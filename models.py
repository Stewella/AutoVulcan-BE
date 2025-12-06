from sqlalchemy import Column, String, Text, DateTime, Integer, Boolean
from datetime import datetime

from db import Base

class Execution(Base):
    __tablename__ = "executions"

    id = Column(String, primary_key=True, index=True)
    status = Column(String, default="running")
    logs = Column(Text, nullable=True)  # store JSON array of log strings
    result_json = Column(Text, nullable=True)  # final result JSON as text
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
    # Optional: store original request for auditing
    request_json = Column(Text, nullable=True)

# --- Auth models ---
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    # store full name as optional to maintain backward compatibility
    full_name = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)