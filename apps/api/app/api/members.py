
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
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
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    search: str = Query(default="", max_length=200),
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

    # Scope every query to the current admin's organization.
    statement = select(User).where(
        User.organization_id == current_user.organization_id
    )

    count_statement = (
        select(func.count())
        .select_from(User)
        .where(User.organization_id == current_user.organization_id)
    )

    # Search by name or email, ignoring surrounding whitespace.
    search_term = search.strip()

    if search_term:
        search_filter = or_(
            User.name.ilike(f"%{search_term}%"),
            User.email.ilike(f"%{search_term}%"),
        )

        statement = statement.where(search_filter)
        count_statement = count_statement.where(search_filter)

    # Count matching members before pagination.
    total = db.execute(count_statement).scalar_one()

    # Apply stable ordering and pagination.
    statement = (
        statement
        .order_by(User.name, User.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    members = db.execute(statement).scalars().all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
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
    if member.id == current_user.id and request.role != "admin":
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
