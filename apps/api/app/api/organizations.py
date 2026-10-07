import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import require_same_organization
from app.db.session import get_db
from app.repositories.organization_repository import get_organization_by_id


router = APIRouter(
    prefix="/api/organizations",
    tags=["Organizations"],
)


def get_organization(
    organization_id: str,
    current_user=Depends(require_same_organization),
    db: Session = Depends(get_db),
):

    try:
        organization_uuid = uuid.UUID(organization_id)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid organization ID",
        )

    organization = get_organization_by_id(
        db,
        organization_uuid,
    )

    if not organization:
        raise HTTPException(
            status_code=404,
            detail="Organization not found",
        )

    return {
        "id": str(organization.id),
        "name": organization.name,
        "slug": organization.slug,
    }