from pydantic import BaseModel
from typing import Optional, Dict, Any, List
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
    is_active: bool
    created_at: datetime

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class TokenPayload(BaseModel):
    sub: str
    exp: Optional[int] = None