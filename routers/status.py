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
