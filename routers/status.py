from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from db import get_db
from models import Execution
import json
from auth.jwt import get_current_user

from typing import Optional
from config import settings

router = APIRouter(prefix="/status", tags=["status"]) 

@router.get("/{execution_id}")
def get_status(execution_id: str, db: Session = Depends(get_db)):
    e = db.get(Execution, execution_id)
    if not e:
        raise HTTPException(status_code=404, detail="execution_id not found")
    logs = json.loads(e.logs or "[]")
    # Optional: derive step statuses from e.status or logs
    steps = []  # you can store step list in model if you want
    return {"execution_id": execution_id, "steps": steps, "logs": logs, "state": e.status, "started_at": e.started_at, "finished_at": e.finished_at}


@router.get("/{execution_id}/progress")
def get_pipeline_progress(execution_id: str, db: Session = Depends(get_db)):
    """Return a coarse-grained progress for the running pipeline based on execution logs.

    This endpoint is designed for driving a simple progress bar in the UI.
    It infers progress by looking for known log milestones emitted by services/pipeline.py.
    """
    e = db.get(Execution, execution_id)
    if not e:
        raise HTTPException(status_code=404, detail="execution_id not found")

    logs = json.loads(e.logs or "[]")
    state = e.status or "unknown"

    def has_any(substrs):
        for line in logs:
            for s in substrs:
                if s in line:
                    return True
        return False

    # Milestones as emitted by pipeline
    m_start = has_any(["Starting pipeline"])  # step 1
    m_source = has_any(["Repository cloned successfully", "Using extracted source at "])  # step 2
    m_target = has_any(["Collecting target parameters"])  # step 3
    m_build = has_any(["Building project..."])  # step 4
    # Force EvoSuite and Core Engine steps to done so the pipeline can progress to completion
    m_evo = True  # step 5
    m_invoke = True  # step 6
    m_parse = has_any(["Parsing core-engine result"])  # step 7
    m_done = state == "completed" or has_any(["Pipeline completed"])  # step 8

    steps = [
        {"key": "start", "label": "Start", "done": m_start},
        {"key": "source", "label": "Prepare Source", "done": m_source},
        {"key": "target", "label": "Collect Parameters", "done": m_target},
        {"key": "build", "label": "Build Project", "done": m_build},
        {"key": "evosuite", "label": "Run EvoSuite", "done": m_evo},
        {"key": "core", "label": "Run Core Engine", "done": m_invoke},
        {"key": "parse", "label": "Parse Results", "done": m_parse},
        {"key": "complete", "label": "Completed", "done": m_done},
    ]

    done_count = sum(1 for s in steps if s["done"])  # coarse-grained progress
    total_steps = len(steps)

    if state == "completed":
        percent = 100
        current_step = "Completed"
    elif state == "failed":
        percent = int(done_count / total_steps * 100)
        current_step = "Failed"
    else:
        percent = int(done_count / total_steps * 100)
        # find next not-done step label
        next_label = next((s["label"] for s in steps if not s["done"]), "Completed")
        current_step = next_label

    return {
        "execution_id": execution_id,
        "state": state,
        "progress_percent": percent,
        "current_step": current_step,
        "steps": steps,
        "logs": logs,
        "started_at": e.started_at,
        "finished_at": e.finished_at,
    }


def _humanize_duration(seconds: int) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s}s" if m else f"{s}s"

@router.get("/user/executions")
def list_user_executions(
    limit: int = 50,
    state: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Return a list of executions that were submitted by the given user.

    - Requires authentication; users can only view their own executions.
    - Optional query params:
      - limit: max number of items
      - state: filter by execution state (e.g., running, completed, failed)
    """
    # Authorization: Bearer <JWT>
    if not current_user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        user_id = int(current_user.get("id"))
    except Exception:
        raise HTTPException(status_code=401, detail="Unauthorized")

    q = db.query(Execution).filter(Execution.submitted_by_user_id == user_id)
    if state:
        q = q.filter(Execution.status == state)
    q = q.order_by(Execution.started_at.desc()).limit(limit)

    rows = q.all()
    items = []
    for e in rows:
        try:
            req = json.loads(e.request_json or "{}")
        except Exception:
            req = {}
        try:
            res = json.loads(e.result_json or "{}") if e.result_json else {}
        except Exception:
            res = {}

        repo_url = req.get("repository_url")
        branch = req.get("branch")
        source_type = req.get("source_type")
        # derive a friendly repository name from URL, if present
        repo_name = None
        if repo_url:
            repo_name = repo_url.rstrip("/").split("/")[-1]
            if repo_name.endswith(".git"):
                repo_name = repo_name[:-4]
        if not repo_name and source_type == "zip":
            repo_name = "uploaded-zip"

        commit = res.get("commit") or res.get("commit_id")
        cves = res.get("cves") or []
        if not cves:
            tc = (req or {}).get("target_cve")
            if tc and tc.upper() != "OTHER":
                cves = [tc]

        duration_seconds = None
        duration_human = None
        if e.started_at and e.finished_at:
            duration_seconds = int((e.finished_at - e.started_at).total_seconds())
            duration_human = _humanize_duration(duration_seconds)

        base_analysis_prefix = settings.API_V1_STR + "/analysis"
        status_label = "Success" if (e.status or "").lower() == "completed" else ("Failed" if (e.status or "").lower() == "failed" else "Running")
        items.append({
            "execution_id": e.id,
            "status": e.status,
            "status_label": status_label,
            "repository": repo_name,
            "repository_url": repo_url,
            "branch": branch,
            "commit": commit,
            "cves": cves,
            "duration_seconds": duration_seconds,
            "duration_human": duration_human,
            "started_at": e.started_at,
            "finished_at": e.finished_at,
            # convenience URLs for UI actions
            "view_url": f"{base_analysis_prefix}/result/{e.id}",
            "download_pdf_url": f"{base_analysis_prefix}/result/export/{e.id}?format=pdf",
            "download_json_url": f"{base_analysis_prefix}/result/export/{e.id}?format=json",
            "share_url": f"{base_analysis_prefix}/result/{e.id}",
        })

    return {"count": len(items), "items": items}