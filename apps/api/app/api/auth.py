
import uuid
import hashlib
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.invitation import OrganizationInvitation
from app.models.user import User
from app.schemas.auth import InvitationAcceptRequest

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import (
    create_access_token,
    get_current_user_id,
    hash_password,
    verify_password,
)
from app.db.session import get_db
from app.repositories.user_repository import create_user, get_user_by_email
from app.schemas.auth import LoginRequest, RegisterRequest


router = APIRouter(
    prefix="/api/auth",
    tags=["Authentication"],
)


@router.post("/register")
def register(
    request: RegisterRequest,
    db: Session = Depends(get_db),
):
    existing_user = get_user_by_email(db, request.email)

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User with this email already exists",
        )

    try:
        organization_id = uuid.UUID(request.organization_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid organization ID",
        )

    user = create_user(
        db=db,
        organization_id=organization_id,
        name=request.name,
        email=request.email,
        password_hash=hash_password(request.password),
    )

    return {
        "message": "User registered successfully",
        "user": {
            "id": str(user.id),
            "name": user.name,
            "email": user.email,
            "role": user.role,
            "organization_id": str(user.organization_id),
        },
    }


@router.post("/login")
def login(
    request: LoginRequest,
    db: Session = Depends(get_db),
):
    user = get_user_by_email(db, request.email)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    access_token = create_access_token(
        user_id=str(user.id),
    )

    return {
        "message": "Login successful",
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": str(user.id),
            "name": user.name,
            "email": user.email,
            "role": user.role,
            "organization_id": str(user.organization_id),
        },
    }

@router.get("/me")
def get_me(
    user_id: str = Depends(get_current_user_id),
):
    return {
        "message": "You are authenticated",
        "user_id": user_id,
    }


@router.post("/accept-invitation")
def accept_invitation(
    request: InvitationAcceptRequest,
    db: Session = Depends(get_db),
):
    # Hash the supplied token; the raw token is never stored.
    token_hash = hashlib.sha256(
        request.token.encode("utf-8")
    ).hexdigest()

    try:
        # Lock the invitation row to prevent simultaneous acceptance.
        statement = (
            select(OrganizationInvitation)
            .where(OrganizationInvitation.token_hash == token_hash)
            .with_for_update()
        )

        invitation = db.execute(
            statement
        ).scalar_one_or_none()

        if invitation is None:
            raise HTTPException(
                status_code=400,
                detail="Invalid invitation",
            )

        if invitation.accepted_at is not None:
            raise HTTPException(
                status_code=400,
                detail="Invitation has already been accepted",
            )

        if invitation.revoked_at is not None:
            raise HTTPException(
                status_code=400,
                detail="Invitation has been revoked",
            )

        if invitation.expires_at <= datetime.now(timezone.utc):
            raise HTTPException(
                status_code=400,
                detail="Invitation has expired",
            )

        # Prevent registration if the email already exists.
        existing_user = db.execute(
            select(User).where(
                User.email == invitation.email
            )
        ).scalar_one_or_none()

        if existing_user is not None:
            raise HTTPException(
                status_code=409,
                detail="An account with this email already exists",
            )

        # Use the invitation's organization, email, and role.
        user = User(
            organization_id=invitation.organization_id,
            name=request.name.strip(),
            email=invitation.email,
            password_hash=hash_password(request.password),
            role=invitation.role,
        )

        invitation.accepted_at = datetime.now(timezone.utc)

        db.add(user)
        db.commit()
        db.refresh(user)

        return {
            "message": "Invitation accepted and account created successfully",
            "user": {
                "id": str(user.id),
                "name": user.name,
                "email": user.email,
                "role": user.role,
                "organization_id": str(user.organization_id),
            },
        }

    except HTTPException:
        db.rollback()
        raise

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Account already exists or invitation could not be accepted",
        )

    except Exception:
        db.rollback()
        raise
