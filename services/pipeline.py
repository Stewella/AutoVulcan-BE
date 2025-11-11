import asyncio
from sqlalchemy.orm import Session
from crud import create_execution, update_execution_logs, update_execution_result
from services.core_client import call_core_engine_http, call_core_engine_via_docker
import json
import os

# helper to run in background via BackgroundTasks
def new_execution_id():
    from uuid import uuid4
    return f"exec-{uuid4().hex[:12]}"

def schedule_pipeline(execution_id: str, request_obj: dict):
    """
    Entry called by BackgroundTasks; will open a DB session, create execution and then run async loop.
    We keep it synchronous wrapper to be BackgroundTasks-friendly.
    """
    # create DB session
    from db import SessionLocal
    db = SessionLocal()
    try:
        create_execution(db, execution_id, request_obj)
        # run actual async pipeline with asyncio loop
        import asyncio
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
        add_log("Fetching repository...")
        await asyncio.sleep(1)

        add_log("Building project...")
        await asyncio.sleep(2)

        add_log("Invoking core-engine...")
        # Choose one method: HTTP or Docker exec
        core_res = None
        try:
            core_res = call_core_engine_http({"request": req})
            add_log("core-engine HTTP call completed")
        except Exception as e_http:
            add_log(f"core-engine HTTP failed: {e_http}, trying docker exec fallback")
            try:
                core_res = call_core_engine_via_docker("core_engine_container", ["java","-jar","/app/core.jar","--json", json.dumps(req)])
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
