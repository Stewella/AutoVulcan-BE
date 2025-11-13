from sqlalchemy import Column, String, Text, DateTime
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