from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.security import (
    require_admin,
    require_same_organization,
)
from app.db.session import get_db
from app.repositories.organization_repository import (
    get_organization_by_id,
    update_organization,
)
from app.schemas.organization import OrganizationUpdateRequest


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
@router.put("/{organization_id}")
def update_organization_details(
    organization_id: str,
    request: OrganizationUpdateRequest,
    current_user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    if str(current_user.organization_id) != organization_id:
        raise HTTPException(
            status_code=403,
            detail="Access denied for this organization",
        )

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

    organization = update_organization(
        db,
        organization,
        request.name,
        request.slug,
    )

    return {
        "message": "Organization updated successfully",
        "organization": {
            "id": str(organization.id),
            "name": organization.name,
            "slug": organization.slug,
        },
    }