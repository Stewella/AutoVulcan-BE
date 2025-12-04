from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session
from db import get_db
from schemas import RunRequest, RunResponse, CallGraphResponse, CVEOption
from services.pipeline import new_execution_id, schedule_pipeline
from auth.jwt import get_current_user
from datetime import datetime
from fastapi import File, UploadFile, Form
from typing import Optional
import os
import zipfile

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

@router.post("/submit/repo", response_model=RunResponse, summary="Submit analysis via repository URL")
def submit_repo(
    background_tasks: BackgroundTasks,
    repository_url: str = Form(..., description="Git repository URL to fetch"),
    target_cve: CVEOption = Form(..., description="Target CVE to analyze"),
    target_method: Optional[str] = Form(None, description="Method to focus on"),
    target_line: Optional[int] = Form(None, description="Line number to focus on"),
    timeout_seconds: Optional[int] = Form(600, description="Timeout for analysis in seconds"),
    current_user=Depends(get_current_user)
):
    exec_id = new_execution_id()
    request_obj = {
        "source_type": "repo",
        "repository_url": repository_url,
        "target_cve": target_cve.value if isinstance(target_cve, CVEOption) else target_cve,
        "target_method": target_method,
        "target_line": target_line,
        "timeout_seconds": timeout_seconds,
        "submitted_by": current_user.get("username")
    }
    background_tasks.add_task(schedule_pipeline, exec_id, request_obj)
    return RunResponse(status="success", execution_id=exec_id, message="Repository submission received", started_at=datetime.utcnow())

@router.post("/submit/zip", response_model=RunResponse, summary="Submit analysis via uploaded ZIP")
def submit_zip(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="ZIP file containing source code"),
    target_cve: CVEOption = Form(..., description="Target CVE to analyze"),
    target_method: Optional[str] = Form(None, description="Method to focus on"),
    target_line: Optional[int] = Form(None, description="Line number to focus on"),
    timeout_seconds: Optional[int] = Form(600, description="Timeout for analysis in seconds"),
    current_user=Depends(get_current_user)
):
    if file.content_type not in ("application/zip", "application/x-zip-compressed", "multipart/x-zip"):
        raise HTTPException(status_code=400, detail="Uploaded file must be a ZIP archive")

    exec_id = new_execution_id()
    base_dir = os.path.join("/tmp/executions", exec_id)
    os.makedirs(base_dir, exist_ok=True)
    zip_path = os.path.join(base_dir, "upload.zip")

    # Save uploaded ZIP
    with open(zip_path, "wb") as out:
        while True:
            chunk = file.file.read(8192)
            if not chunk:
                break
            out.write(chunk)

    # Extract ZIP
    extract_dir = os.path.join(base_dir, "source")
    os.makedirs(extract_dir, exist_ok=True)
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_dir)
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Invalid ZIP file")

    request_obj = {
        "source_type": "zip",
        "source_path": extract_dir,
        "target_cve": target_cve.value if isinstance(target_cve, CVEOption) else target_cve,
        "target_method": target_method,
        "target_line": target_line,
        "timeout_seconds": timeout_seconds,
        "submitted_by": current_user.get("username")
    }
    background_tasks.add_task(schedule_pipeline, exec_id, request_obj)
    return RunResponse(status="success", execution_id=exec_id, message="ZIP submission received", started_at=datetime.utcnow())