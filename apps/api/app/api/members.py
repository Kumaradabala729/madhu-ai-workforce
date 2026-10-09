
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import require_admin
from app.db.session import get_db
from app.models.user import User
from app.schemas.member import MemberRoleUpdateRequest


router = APIRouter(
    prefix="/api/organizations",
    tags=["Organization Members"],
)


@router.get("/{organization_id}/members")
def list_organization_members(
    organization_id: str,
    current_user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    # Validate the organization ID.
    try:
        organization_uuid = uuid.UUID(organization_id)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid organization ID",
        )

    # Restrict access to the admin's own organization.
    if current_user.organization_id != organization_uuid:
        raise HTTPException(
            status_code=403,
            detail="Access denied for this organization",
        )

    statement = (
        select(User)
        .where(
            User.organization_id == current_user.organization_id
        )
        .order_by(User.name)
    )

    members = db.execute(statement).scalars().all()

    return {
        "total": len(members),
        "members": [
            {
                "id": str(member.id),
                "name": member.name,
                "email": member.email,
                "role": member.role,
            }
            for member in members
        ],
    }


@router.patch("/{organization_id}/members/{member_id}/role")
def update_member_role(
    organization_id: str,
    member_id: str,
    request: MemberRoleUpdateRequest,
    current_user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    # Validate the organization ID.
    try:
        organization_uuid = uuid.UUID(organization_id)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid organization ID",
        )

    # Restrict access to the admin's own organization.
    if current_user.organization_id != organization_uuid:
        raise HTTPException(
            status_code=403,
            detail="Access denied for this organization",
        )

    # Validate the member ID.
    try:
        member_uuid = uuid.UUID(member_id)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid member ID",
        )

    # Find the member only within the admin's organization.
    statement = select(User).where(
        User.id == member_uuid,
        User.organization_id == current_user.organization_id,
    )

    member = db.execute(statement).scalar_one_or_none()

    if member is None:
        raise HTTPException(
            status_code=404,
            detail="Member not found",
        )

    # Prevent an admin from removing their own admin role.
    if (
        member.id == current_user.id
        and request.role != "admin"
    ):
        raise HTTPException(
            status_code=400,
            detail="You cannot remove your own admin role",
        )

    # Update the member's role.
    member.role = request.role

    try:
        db.commit()
        db.refresh(member)
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to update member role",
        )

    return {
        "message": "Member role updated successfully",
        "member": {
            "id": str(member.id),
            "name": member.name,
            "email": member.email,
            "role": member.role,
        },
    }

