from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.organization import Organization


def get_organization_by_id(
    db: Session,
    organization_id,
) -> Optional[Organization]:
    statement = select(Organization).where(
        Organization.id == organization_id
    )

    return db.execute(statement).scalar_one_or_none()