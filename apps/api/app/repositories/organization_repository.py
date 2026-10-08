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
def update_organization(
    db: Session,
    organization: Organization,
    name: str,
    slug: str,
) -> Organization:
    organization.name = name
    organization.slug = slug

    db.commit()
    db.refresh(organization)

    return organization