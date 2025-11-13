from sqlalchemy.orm import Session
from datetime import datetime
import json

from models import Execution


def create_execution(db: Session, execution_id: str, request_obj: dict) -> Execution:
    e = Execution(
        id=execution_id,
        status="running",
        logs=json.dumps([]),
        started_at=datetime.utcnow(),
        request_json=json.dumps(request_obj or {}),
    )
    db.add(e)
    db.commit()
    db.refresh(e)
    return e


def update_execution_logs(db: Session, exec_id: str, logs: list[str]) -> None:
    e = db.query(Execution).get(exec_id)
    if not e:
        return
    e.logs = json.dumps(logs)
    db.commit()


def update_execution_result(db: Session, exec_id: str, result: dict, status: str = "completed") -> None:
    e = db.query(Execution).get(exec_id)
    if not e:
        return
    e.result_json = json.dumps(result or {})
    e.status = status
    e.finished_at = datetime.utcnow()
    db.commit()