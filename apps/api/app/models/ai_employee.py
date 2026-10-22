
import uuid
from typing import Optional

from sqlalchemy import ForeignKey, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AIEmployee(Base):
    __tablename__ = "ai_employees"

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

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    role: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="sales",
        server_default="sales",
    )

    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    language: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="en",
        server_default="en",
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="draft",
        server_default="draft",
    )
