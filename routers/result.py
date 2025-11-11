from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from db import get_db
from models import Execution
import json
from utils.pdf import build_simple_pdf
from fastapi.responses import FileResponse, JSONResponse

router = APIRouter(prefix="/result", tags=["result"])

@router.get("/{execution_id}")
def get_result(execution_id: str, db: Session = Depends(get_db)):
    e = db.get(Execution, execution_id)
    if not e:
        raise HTTPException(status_code=404, detail="execution_id not found")
    if not e.result_json:
        raise HTTPException(status_code=404, detail="result not ready")
    return JSONResponse(json.loads(e.result_json))

@router.get("/export/{execution_id}")
def export_result(execution_id: str, format: str = "json", db: Session = Depends(get_db)):
    e = db.get(Execution, execution_id)
    if not e:
        raise HTTPException(status_code=404, detail="execution_id not found")
    if not e.result_json:
        raise HTTPException(status_code=404, detail="result not ready")
    result = json.loads(e.result_json)
    if format.lower() == "json":
        return JSONResponse({"execution_id": execution_id, "result": result})
    if format.lower() == "pdf":
        out_path = f"/tmp/{execution_id}.pdf"
        build_simple_pdf(result, out_path)
        return FileResponse(out_path, filename=f"{execution_id}.pdf", media_type="application/pdf")
    raise HTTPException(status_code=400, detail="format must be json or pdf")
