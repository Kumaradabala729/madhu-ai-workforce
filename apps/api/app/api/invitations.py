import uuid
from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import require_admin
from app.db.session import get_db
from app.models.invitation import OrganizationInvitation
from app.schemas.invitation import (
    InvitationCreateRequest,
    InvitationCreateResponse,
)
from app.services.invitation_service import create_invitation


router = APIRouter(
    prefix="/api/organizations",
    tags=["Organization Invitations"],
)


def parse_uuid(value: str, message: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(status_code=400, detail=message)


def get_invitation_status(invitation: OrganizationInvitation) -> str:
    if invitation.accepted_at is not None:
        return "accepted"

    if invitation.revoked_at is not None:
        return "revoked"

    if invitation.expires_at <= datetime.now(timezone.utc):
        return "expired"

    return "pending"


@router.post(
    "/{organization_id}/invitations",
    response_model=InvitationCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_organization_invitation(
    organization_id: str,
    request: InvitationCreateRequest,
    current_user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    organization_uuid = parse_uuid(
        organization_id,
        "Invalid organization ID",
    )

    if current_user.organization_id != organization_uuid:
        raise HTTPException(
            status_code=403,
            detail="Access denied for this organization",
        )

    email = str(request.email).strip().lower()
    now = datetime.now(timezone.utc)

    existing_statement = select(OrganizationInvitation).where(
        OrganizationInvitation.organization_id == organization_uuid,
        OrganizationInvitation.email == email,
        OrganizationInvitation.accepted_at.is_(None),
        OrganizationInvitation.revoked_at.is_(None),
        OrganizationInvitation.expires_at > now,
    )

    existing = db.execute(existing_statement).scalar_one_or_none()

    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="An active invitation already exists for this email",
        )

    from app.models.user import User

    user_statement = select(User).where(
        User.organization_id == organization_uuid,
        User.email == email,
    )

    existing_user = db.execute(user_statement).scalar_one_or_none()

    if existing_user is not None:
        raise HTTPException(
            status_code=409,
            detail="This email already belongs to an organization member",
        )

    try:
        invitation, raw_token = create_invitation(
            db=db,
            organization_id=organization_uuid,
            email=email,
            role=request.role,
            invited_by=current_user.id,
        )
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Could not create invitation; please try again",
        )

    invite_url = (
        "http://localhost:3000/accept-invitation?token="
        + quote(raw_token, safe="")
    )

    return InvitationCreateResponse(
        id=str(invitation.id),
        email=invitation.email,
        role=invitation.role,
        expires_at=invitation.expires_at.isoformat(),
        invite_url=invite_url,
    )


@router.get("/{organization_id}/invitations")
def list_organization_invitations(
    organization_id: str,
    current_user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    organization_uuid = parse_uuid(
        organization_id,
        "Invalid organization ID",
    )

    if current_user.organization_id != organization_uuid:
        raise HTTPException(
            status_code=403,
            detail="Access denied for this organization",
        )

    statement = (
        select(OrganizationInvitation)
        .where(
            OrganizationInvitation.organization_id == organization_uuid
        )
        .order_by(OrganizationInvitation.created_at.desc())
    )

    invitations = db.execute(statement).scalars().all()

    results = []

    for invitation in invitations:
        results.append(
            {
                "id": str(invitation.id),
                "email": invitation.email,
                "role": invitation.role,
                "status": get_invitation_status(invitation),
                "created_at": invitation.created_at.isoformat(),
                "expires_at": invitation.expires_at.isoformat(),
                "accepted_at": (
                    invitation.accepted_at.isoformat()
                    if invitation.accepted_at
                    else None
                ),
                "revoked_at": (
                    invitation.revoked_at.isoformat()
                    if invitation.revoked_at
                    else None
                ),
            }
        )

    return {
        "total": len(results),
        "invitations": results,
    }


@router.post("/{organization_id}/invitations/{invitation_id}/revoke")
def revoke_organization_invitation(
    organization_id: str,
    invitation_id: str,
    current_user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    organization_uuid = parse_uuid(
        organization_id,
        "Invalid organization ID",
    )
    invitation_uuid = parse_uuid(
        invitation_id,
        "Invalid invitation ID",
    )

    if current_user.organization_id != organization_uuid:
        raise HTTPException(
            status_code=403,
            detail="Access denied for this organization",
        )

    statement = select(OrganizationInvitation).where(
        OrganizationInvitation.id == invitation_uuid,
        OrganizationInvitation.organization_id == organization_uuid,
    )

    invitation = db.execute(statement).scalar_one_or_none()

    if invitation is None:
        raise HTTPException(
            status_code=404,
            detail="Invitation not found",
        )

    if invitation.accepted_at is not None:
        raise HTTPException(
            status_code=409,
            detail="An accepted invitation cannot be revoked",
        )

    if invitation.revoked_at is not None:
        raise HTTPException(
            status_code=409,
            detail="Invitation has already been revoked",
        )

    if invitation.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(
            status_code=409,
            detail="An expired invitation cannot be revoked",
        )

    invitation.revoked_at = datetime.now(timezone.utc)

    try:
        db.commit()
        db.refresh(invitation)
    except Exception:
        db.rollback()
        raise

    return {
        "message": "Invitation revoked successfully",
        "id": str(invitation.id),
        "email": invitation.email,
        "status": get_invitation_status(invitation),
        "revoked_at": invitation.revoked_at.isoformat(),
    }