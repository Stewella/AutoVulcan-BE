from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime

class RunRequest(BaseModel):
    repository_url: Optional[str] = None
    branch: Optional[str] = None
    options: Optional[Dict[str, Any]] = None

    class Config:
        extra = "allow"  # allow additional fields without validation errors

class RunResponse(BaseModel):
    status: str
    execution_id: str
    message: str
    started_at: datetime