
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.invitation import OrganizationInvitation


INVITATION_EXPIRY_HOURS = 48


def create_invitation(
    db: Session,
    organization_id,
    email: str,
    role: str,
    invited_by,
):
    """Create an invitation and return it with its one-time raw token."""

    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    expires_at = datetime.now(timezone.utc) + timedelta(
        hours=INVITATION_EXPIRY_HOURS
    )

    invitation = OrganizationInvitation(
        organization_id=organization_id,
        email=email.strip().lower(),
        role=role,
        token_hash=token_hash,
        invited_by=invited_by,
        expires_at=expires_at,
    )

    db.add(invitation)
    db.commit()
    db.refresh(invitation)

    # The raw token is returned only once for creating a development invite URL.
    return invitation, raw_token
