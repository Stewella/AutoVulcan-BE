from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from db import get_db
from models import Execution
import json

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
    m_evo = has_any(["Running EvoSuite...", "EvoSuite completed", "EvoSuite failed"])  # step 5
    m_invoke = has_any(["Invoking core-engine...", "core-engine HTTP call completed", "core-engine docker exec completed"])  # step 6
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
