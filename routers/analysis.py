from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session
from db import get_db
from schemas import RunRequest, RunResponse, CallGraphResponse
from services.pipeline import new_execution_id, schedule_pipeline
from auth.jwt import get_current_user
from datetime import datetime
from fastapi import File, UploadFile, Form
from typing import Optional
import os
import zipfile
import re
import json
from crud import create_execution
from models import Execution

router = APIRouter(prefix="/analysis", tags=["analysis"])

# -----------------------------
# Module-level constants & helpers
# -----------------------------
ALLOWED_ZIP_TYPES = {
    "application/zip",
    "application/x-zip-compressed",
    "multipart/x-zip",
}

SAMPLE_CALL_GRAPH = {
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
            {"id": "n10", "label": "PrintStream.println()", "type": "intermediate"},
            {"id": "n11", "label": "ServiceB.transform()", "type": "intermediate"},
            {"id": "n12", "label": "String.toUpperCase()", "type": "intermediate"},
            {"id": "n13", "label": "Object.<init>()", "type": "intermediate"},
            {"id": "n14", "label": "ServiceA.<init>()", "type": "intermediate"},
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
            {"source": "n14", "target": "n13"},
        ],
    }
}


def normalize_cve(cve: str) -> str:
    """Return CVE as string (already validated and normalized upstream)."""
    return cve


def schedule_exec(background_tasks: BackgroundTasks, exec_id: str, request_obj: dict) -> None:
    """Schedule the pipeline execution in the background."""
    background_tasks.add_task(schedule_pipeline, exec_id, request_obj)


def make_request_obj(
    *,
    source_type: str,
    target_cve: str,
    target_method: Optional[str],
    target_line: Optional[int],
    timeout_seconds: int,
    submitted_by: Optional[str],
    submitted_by_user_id: Optional[int] = None,
    repository_url: Optional[str] = None,
    source_path: Optional[str] = None,
) -> dict:
    """Build a standardized request object for the pipeline."""
    base = {
        "source_type": source_type,
        "target_cve": normalize_cve(target_cve),
        "target_method": target_method,
        "target_line": target_line,
        "timeout_seconds": timeout_seconds,
        "submitted_by": submitted_by,
        "submitted_by_user_id": submitted_by_user_id,
    }
    if repository_url:
        base["repository_url"] = repository_url
    if source_path:
        base["source_path"] = source_path
    return base


def ensure_execution_dir(exec_id: str) -> str:
    """Create and return the base execution directory path for a given execution id."""
    base_dir = os.path.join("/tmp/executions", exec_id)
    os.makedirs(base_dir, exist_ok=True)
    return base_dir


def save_zip(file: UploadFile, zip_path: str) -> None:
    """Save uploaded ZIP file to the specified path in chunks."""
    with open(zip_path, "wb") as out:
        while True:
            chunk = file.file.read(8192)
            if not chunk:
                break
            out.write(chunk)


def extract_zip(zip_path: str, extract_dir: str) -> None:
    """Extract the ZIP file to the given directory, raising HTTP 400 for invalid archives."""
    os.makedirs(extract_dir, exist_ok=True)
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_dir)
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Invalid ZIP file")


# -----------------------------
# Endpoints
# -----------------------------
@router.post("/run", response_model=RunResponse, summary="Start analysis run")
def run_analysis(
    req: RunRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Start an analysis using a flexible JSON body (RunRequest)."""
    exec_id = new_execution_id()
    # Persist execution immediately (optional for /run)
    payload = {**req.dict(), "submitted_by": current_user.get("username"), "submitted_by_user_id": current_user.get("id")}
    create_execution(db, exec_id, payload)
    # schedule pipeline background job which will persist logs/result to DB
    schedule_exec(background_tasks, exec_id, payload)
    return RunResponse(
        status="success",
        execution_id=exec_id,
        message="SEIGE analysis started",
        started_at=datetime.utcnow(),
    )


@router.get("/graph", response_model=CallGraphResponse, summary="Get call graph")
def get_call_graph(execution_id: Optional[str] = None, db: Session = Depends(get_db)):
    """Return a sample call graph. Real call graph not implemented yet."""
    return SAMPLE_CALL_GRAPH


# Accept CVE in format CVE-YYYY-NNNN+ or the literal OTHER; also accept GHSA-xxxx-xxxx-xxxx
CVE_REGEX = re.compile(r"^CVE-\d{4}-\d{4,}$", re.IGNORECASE)
GHSA_REGEX = re.compile(r"^GHSA-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{4}$", re.IGNORECASE)


def validate_cve_format(cve: str) -> str:
    if cve is None:
        raise HTTPException(status_code=400, detail="target_cve is required")
    c = cve.strip()
    if c.upper() == "OTHER":
        return "OTHER"
    if CVE_REGEX.match(c):
        parts = c.split("-")
        return f"CVE-{parts[1]}-{parts[2]}"
    if GHSA_REGEX.match(c):
        parts = c.split("-")
        # normalize to standard GHSA lowercase blocks
        return f"GHSA-{parts[1].lower()}-{parts[2].lower()}-{parts[3].lower()}"
    raise HTTPException(status_code=400, detail="target_cve must follow CVE-YYYY-NNNN+ or GHSA-xxxx-xxxx-xxxx format, or be 'OTHER'")


@router.post("/submit/repo", response_model=RunResponse, summary="Submit analysis via repository URL")
def submit_repo(
    background_tasks: BackgroundTasks,
    repository_url: str = Form(..., description="Git repository URL to fetch"),
    target_cve: str = Form(..., description="Target identifier: CVE-YYYY-NNNN+ or GHSA-xxxx-xxxx-xxxx, or OTHER"),
    target_method: Optional[str] = Form(None, description="Method to focus on"),
    target_line: Optional[int] = Form(None, description="Line number to focus on"),
    timeout_seconds: Optional[int] = Form(600, description="Timeout for analysis in seconds"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Submit an analysis job by providing a repository URL and target parameters."""
    target_cve_clean = validate_cve_format(target_cve)
    exec_id = new_execution_id()
    request_obj = make_request_obj(
        source_type="repo",
        repository_url=repository_url,
        target_cve=target_cve_clean,
        target_method=target_method,
        target_line=target_line,
        timeout_seconds=timeout_seconds or 600,
        submitted_by=current_user.get("username"),
        submitted_by_user_id=current_user.get("id"),
    )
    # Persist execution immediately
    create_execution(db, exec_id, request_obj)
    schedule_exec(background_tasks, exec_id, request_obj)
    return RunResponse(
        status="success",
        execution_id=exec_id,
        message="Repository submission received",
        started_at=datetime.utcnow(),
    )


@router.post("/submit/zip", response_model=RunResponse, summary="Submit analysis via uploaded ZIP")
def submit_zip(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="ZIP file containing source code"),
    target_cve: str = Form(..., description="Target identifier: CVE-YYYY-NNNN+ or GHSA-xxxx-xxxx-xxxx, or OTHER"),
    target_method: Optional[str] = Form(None, description="Method to focus on"),
    target_line: Optional[int] = Form(None, description="Line number to focus on"),
    timeout_seconds: Optional[int] = Form(600, description="Timeout for analysis in seconds"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Submit an analysis job by uploading a ZIP archive of source code."""
    if file.content_type not in ALLOWED_ZIP_TYPES:
        raise HTTPException(status_code=400, detail="Uploaded file must be a ZIP archive")

    target_cve_clean = validate_cve_format(target_cve)

    exec_id = new_execution_id()
    base_dir = ensure_execution_dir(exec_id)

    # Save and extract ZIP
    zip_path = os.path.join(base_dir, "upload.zip")
    save_zip(file, zip_path)
    extract_dir = os.path.join(base_dir, "source")
    extract_zip(zip_path, extract_dir)

    request_obj = make_request_obj(
        source_type="zip",
        source_path=extract_dir,
        target_cve=target_cve_clean,
        target_method=target_method,
        target_line=target_line,
        timeout_seconds=timeout_seconds or 600,
        submitted_by=current_user.get("username"),
        submitted_by_user_id=current_user.get("id"),
    )
    # Persist execution immediately
    create_execution(db, exec_id, request_obj)
    schedule_exec(background_tasks, exec_id, request_obj)
    return RunResponse(
        status="success",
        execution_id=exec_id,
        message="ZIP submission received",
        started_at=datetime.utcnow(),
    )