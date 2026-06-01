from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    func
)
from app.db.base_class import Base

class ControlTestResult(Base): 

    __tablename__ = "control_test_results"

    id = Column(Integer, primary_key=True)

    test_id = Column(Integer, nullable=False)

    control_id = Column(String, nullable=False)

    cycle_id = Column(Integer, nullable=False)

    compliance_test = Column(String, nullable=False)

    audit_justification = Column(Text)

    task_id = Column(String)

    execution_time_ms = Column(Integer)

    execution_status = Column(String , default = "NOT-STARTED")

    user_id = Column(String)

    # NEW FIELDS
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )