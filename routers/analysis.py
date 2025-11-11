from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session
from db import get_db
from schemas import RunRequest, RunResponse
from services.pipeline import new_execution_id, schedule_pipeline
from auth.jwt import get_current_user
from datetime import datetime

router = APIRouter(prefix="/analysis", tags=["analysis"])

@router.post("/run", response_model=RunResponse)
def run_analysis(req: RunRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    # create execution id and DB record
    exec_id = new_execution_id()
    # schedule pipeline background job which will persist logs/result to DB
    # schedule_pipeline returns immediately
    background_tasks.add_task(schedule_pipeline, exec_id, req.dict())
    return RunResponse(status="success", execution_id=exec_id, message="SEIGE analysis started", started_at=datetime.utcnow())
