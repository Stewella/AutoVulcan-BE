from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session
from db import get_db
from schemas import RunRequest, RunResponse, CallGraphResponse
from services.pipeline import new_execution_id, schedule_pipeline
from auth.jwt import get_current_user
from datetime import datetime

router = APIRouter(prefix="/analysis", tags=["analysis"])

@router.post("/run", response_model=RunResponse, summary="Start analysis run")
def run_analysis(req: RunRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    # create execution id and DB record
    exec_id = new_execution_id()
    # schedule pipeline background job which will persist logs/result to DB
    # schedule_pipeline returns immediately
    background_tasks.add_task(schedule_pipeline, exec_id, req.dict())
    return RunResponse(status="success", execution_id=exec_id, message="SEIGE analysis started", started_at=datetime.utcnow())

@router.get("/graph", response_model=CallGraphResponse, summary="Get call graph")
def get_call_graph():
    return {
        "callGraph": {
            "nodes": [
                {"id": "n1",  "label": "MainApp.main()", "type": "entry"},
                {"id": "n2",  "label": "ServiceB.runTask()", "type": "intermediate"},
                {"id": "n3",  "label": "Repository.load()", "type": "intermediate"},
                {"id": "n4",  "label": "Repository.<init>()", "type": "intermediate"},
                {"id": "n5",  "label": "ServiceB.<init>()", "type": "intermediate"},
                {"id": "n6",  "label": "ServiceA.processData()", "type": "intermediate"},
                {"id": "n7",  "label": "Utils.log()", "type": "intermediate"},
                {"id": "n8",  "label": "Utils.printSummary()", "type": "intermediate"},
                {"id": "n9",  "label": "Repository.save()", "type": "intermediate"},
                {"id": "n10", "label": "PrintStream.println()", "type": "system"},
                {"id": "n11", "label": "ServiceB.transform()", "type": "intermediate"},
                {"id": "n12", "label": "String.toUpperCase()", "type": "system"},
                {"id": "n13", "label": "Object.<init>()", "type": "system"},
                {"id": "n14", "label": "ServiceA.<init>()", "type": "intermediate"}
            ],
            "edges": [
                {"source": "n2", "target": "n3"},
                {"source": "n1", "target": "n4"},
                {"source": "n5", "target": "n13"},
                {"source": "n6", "target": "n7"},
                {"source": "n1", "target": "n5"},
                {"source": "n1", "target": "n2"},
                {"source": "n1", "target": "n8"},
                {"source": "n9", "target": "n7"},
                {"source": "n1", "target": "n6"},
                {"source": "n8", "target": "n10"},
                {"source": "n6", "target": "n10"},
                {"source": "n2", "target": "n11"},
                {"source": "n2", "target": "n9"},
                {"source": "n3", "target": "n7"},
                {"source": "n1", "target": "n10"},
                {"source": "n11", "target": "n12"},
                {"source": "n2", "target": "n10"},
                {"source": "n7", "target": "n10"},
                {"source": "n4", "target": "n13"},
                {"source": "n1", "target": "n14"},
                {"source": "n14", "target": "n13"}
            ]
        }
    }
