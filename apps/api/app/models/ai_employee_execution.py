import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AIEmployeeExecution(Base):
    __tablename__ = "ai_employee_executions"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    ai_employee_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    task: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        server_default="pending",
    )

    input_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    output_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
