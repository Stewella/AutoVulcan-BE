from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum

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

class CVEOption(str, Enum):
    CVE_2021_44228 = "CVE-2021-44228"  # Log4Shell
    CVE_2017_5638 = "CVE-2017-5638"    # Apache Struts Jakarta
    CVE_2020_1472 = "CVE-2020-1472"    # Zerologon
    OTHER = "OTHER"                      # Generic/Other

# --- Graph Schemas ---
class GraphNode(BaseModel):
    id: str
    label: str
    type: str

class GraphEdge(BaseModel):
    source: str
    target: str

class CallGraph(BaseModel):
    nodes: List[GraphNode]
    edges: List[GraphEdge]

class CallGraphResponse(BaseModel):
    callGraph: CallGraph

# --- Auth Schemas ---
class UserCreate(BaseModel):
    username: str
    email: str
    password: str

class UserPublic(BaseModel):
    id: int
    username: str
    email: str
    full_name: Optional[str] = None
    is_active: bool
    created_at: datetime

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class TokenPayload(BaseModel):
    sub: str
    exp: Optional[int] = None