import asyncio
from sqlalchemy.orm import Session
from crud import create_execution, update_execution_logs, update_execution_result
from services.core_client import call_core_engine_http, call_core_engine_via_docker
import json
import os
import subprocess

# helper to run in background via BackgroundTasks
def new_execution_id():
    from uuid import uuid4
    return f"exec-{uuid4().hex[:12]}"

def schedule_pipeline(execution_id: str, request_obj: dict):
    """
    Entry called by BackgroundTasks; will open a DB session, create/update execution record and then run async loop.
    We keep it synchronous wrapper to be BackgroundTasks-friendly.
    """
    # create DB session
    from db import SessionLocal
    db = SessionLocal()
    try:
        # ensure execution exists; if already created by the submit endpoint, update status to running
        try:
            from models import Execution  # local import to avoid circular
            existing = db.get(Execution, execution_id)
        except Exception:
            existing = None
        if existing is None:
            create_execution(db, execution_id, request_obj)
        else:
            from datetime import datetime
            existing.status = "running"
            existing.request_json = json.dumps(request_obj or {})
            if not existing.started_at:
                existing.started_at = datetime.utcnow()
            existing.logs = json.dumps([])
            db.commit()
        # run actual async pipeline with asyncio loop
        asyncio.run(_run_pipeline(db, execution_id, request_obj))
    finally:
        db.close()

async def _run_pipeline(db: Session, exec_id: str, req: dict):
    logs = []
    def add_log(msg: str):
        logs.append(msg)
        # persist last N logs every time (to reduce io, you can batch)
        update_execution_logs(db, exec_id, logs)

    try:
        add_log("Starting pipeline")
        # Determine source
        base_dir = os.path.join("/tmp/executions", exec_id)
        os.makedirs(base_dir, exist_ok=True)
        source_path = None
        src_type = req.get("source_type")
        if src_type == "repo":
            repo_url = req.get("repository_url")
            if not repo_url:
                add_log("No repository_url provided for repo source")
                update_execution_result(db, exec_id, {"error": "Missing repository_url"}, status="failed")
                return
            repo_dir = os.path.join(base_dir, "repo")
            os.makedirs(repo_dir, exist_ok=True)
            add_log(f"Cloning repository: {repo_url}")
            p = subprocess.run(["git", "clone", "--depth", "1", repo_url, repo_dir], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if p.returncode != 0:
                add_log(f"git clone failed: {p.stderr}")
                update_execution_result(db, exec_id, {"error": f"git clone failed: {p.stderr}"}, status="failed")
                return
            add_log("Repository cloned successfully")
            source_path = repo_dir
        elif src_type == "zip":
            source_path = req.get("source_path")
            if not source_path or not os.path.isdir(source_path):
                add_log("Invalid or missing source_path for zip source")
                update_execution_result(db, exec_id, {"error": "Invalid source_path"}, status="failed")
                return
            add_log(f"Using extracted source at {source_path}")
        else:
            add_log("Unknown source_type. Expected 'repo' or 'zip'")
            update_execution_result(db, exec_id, {"error": "Unknown source_type"}, status="failed")
            return

        # Target info
        add_log("Collecting target parameters")
        target_cve = req.get("target_cve")
        target_method = req.get("target_method")
        target_line = req.get("target_line")
        timeout_seconds = req.get("timeout_seconds", 600)
        add_log(f"Target: CVE={target_cve}, method={target_method}, line={target_line}, timeout={timeout_seconds}s")

        add_log("Building project...")
        await asyncio.sleep(2)

        add_log("Invoking core-engine...")
        # Choose one method: HTTP or Docker exec
        core_res = None
        payload = {"request": {**req, "source_path": source_path}}
        try:
            core_res = call_core_engine_http(payload, timeout=timeout_seconds)
            add_log("core-engine HTTP call completed")
        except Exception as e_http:
            add_log(f"core-engine HTTP failed: {e_http}, trying docker exec fallback")
            try:
                core_res = call_core_engine_via_docker("core_engine_container", ["java","-jar","/app/core.jar","--json", json.dumps(payload)])
                add_log("core-engine docker exec completed")
            except Exception as e_docker:
                add_log(f"core-engine fallback failed: {e_docker}")
                # mark as failed
                update_execution_result(db, exec_id, {"error": str(e_docker)}, status="failed")
                return

        add_log("Parsing core-engine result")
        # core_res expected to be dict with 'summary' and 'cve_details'
        update_execution_result(db, exec_id, core_res, status="completed")
        add_log("Pipeline completed")
    except Exception as e:
        add_log(f"Pipeline error: {e}")
        update_execution_result(db, exec_id, {"error": str(e)}, status="failed")
