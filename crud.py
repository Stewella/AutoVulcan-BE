from sqlalchemy.orm import Session
from datetime import datetime
import json

from models import Execution, User


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
    e = db.get(Execution, exec_id)
    if not e:
        return
    e.logs = json.dumps(logs)
    db.commit()


def update_execution_result(db: Session, exec_id: str, result: dict, status: str = "completed") -> None:
    e = db.get(Execution, exec_id)
    if not e:
        return
    e.result_json = json.dumps(result or {})
    e.status = status
    e.finished_at = datetime.utcnow()
    db.commit()

# --- User CRUD helpers ---

from typing import Optional


def get_user_by_username(db: Session, username: str) -> Optional[User]:
    return db.query(User).filter(User.username == username).first()


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    return db.query(User).filter(User.email == email).first()


def create_user(db: Session, username: str, email: str, hashed_password: str, full_name: Optional[str] = None) -> User:
    u = User(username=username, email=email, hashed_password=hashed_password, full_name=full_name)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u