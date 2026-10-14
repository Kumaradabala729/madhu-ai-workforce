
import hashlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

from fastapi.testclient import TestClient

from app.main import app
from app.core.security import get_current_user, require_admin
from app.db.session import get_db
from app.models.user import User

client = TestClient(app)

ORGANIZATION_ID = "efdfb6e6-0184-4ff6-9bbb-6a99a57b1fc8"
ADMIN_ID = "f00ccf60-0f09-47ba-ae67-2c7eb2b0d245"
MEMBER_ID = "04d10d2d-c299-4799-96ef-3f0026f4a3fa"
OTHER_ORGANIZATION_ID = "9b84ee15-28a4-4ed3-9719-09af9038f451"

TEST_TOKEN = "madhu-test-invitation-token-123"


def override_admin():
    return SimpleNamespace(
        id=UUID(ADMIN_ID),
        organization_id=UUID(ORGANIZATION_ID),
        role="admin",
    )


def override_member():
    return SimpleNamespace(
        id=UUID(MEMBER_ID),
        organization_id=UUID(ORGANIZATION_ID),
        role="member",
    )


def make_mock_invitation(
    token=TEST_TOKEN,
    accepted_at=None,
    revoked_at=None,
    expires_at=None,
):
    return SimpleNamespace(
        id=UUID("11111111-1111-4111-8111-111111111111"),
        organization_id=UUID(ORGANIZATION_ID),
        email="newmember@example.com",
        role="member",
        token_hash=hashlib.sha256(
            token.encode("utf-8")
        ).hexdigest(),
        invited_by=UUID(ADMIN_ID),
        expires_at=expires_at or (
            datetime.now(timezone.utc) + timedelta(hours=24)
        ),
        accepted_at=accepted_at,
        revoked_at=revoked_at,
    )


def setup_accept_invitation_test(mock_db):
    app.dependency_overrides[get_db] = lambda: mock_db


# ---------------------------------------------------------
# Existing tests
# ---------------------------------------------------------

def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200


def test_invitation_list_requires_authentication():
    response = client.get(
        f"/api/organizations/{ORGANIZATION_ID}/invitations"
    )
    assert response.status_code == 401


def test_admin_invalid_page_returns_422():
    app.dependency_overrides[require_admin] = override_admin
    try:
        response = client.get(
            f"/api/organizations/{ORGANIZATION_ID}/invitations",
            params={"page": 0},
        )
        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_admin_oversized_page_size_returns_422():
    app.dependency_overrides[require_admin] = override_admin
    try:
        response = client.get(
            f"/api/organizations/{ORGANIZATION_ID}/invitations",
            params={"page_size": 101},
        )
        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_member_cannot_access_invitation_list():
    app.dependency_overrides[get_current_user] = override_member
    try:
        response = client.get(
            f"/api/organizations/{ORGANIZATION_ID}/invitations"
        )
        assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_invalid_invitation_status_returns_422():
    app.dependency_overrides[require_admin] = override_admin
    try:
        response = client.get(
            f"/api/organizations/{ORGANIZATION_ID}/invitations",
            params={"invitation_status": "wrong"},
        )
        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_admin_invitation_list_returns_pagination_metadata():
    app.dependency_overrides[require_admin] = override_admin

    mock_db = MagicMock()
    mock_db.execute.return_value.scalar_one.return_value = 0
    mock_db.execute.return_value.scalars.return_value.all.return_value = []

    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        response = client.get(
            f"/api/organizations/{ORGANIZATION_ID}/invitations",
            params={"page": 1, "page_size": 10},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 1
        assert data["page_size"] == 10
        assert data["total"] == 0
        assert data["total_pages"] == 0
        assert data["invitations"] == []
    finally:
        app.dependency_overrides.clear()


def test_admin_invitation_list_accepts_valid_status_filter():
    app.dependency_overrides[require_admin] = override_admin

    mock_db = MagicMock()
    mock_db.execute.return_value.scalar_one.return_value = 0
    mock_db.execute.return_value.scalars.return_value.all.return_value = []

    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        response = client.get(
            f"/api/organizations/{ORGANIZATION_ID}/invitations",
            params={"invitation_status": "pending"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["invitations"] == []
    finally:
        app.dependency_overrides.clear()


def test_admin_cannot_access_another_organizations_invitations():
    app.dependency_overrides[require_admin] = override_admin

    try:
        response = client.get(
            f"/api/organizations/{OTHER_ORGANIZATION_ID}/invitations"
        )

        assert response.status_code == 403
        assert response.json()["detail"] == (
            "Access denied for this organization"
        )
    finally:
        app.dependency_overrides.clear()


def test_invalid_organization_id_returns_400():
    app.dependency_overrides[require_admin] = override_admin

    try:
        response = client.get(
            "/api/organizations/not-a-valid-uuid/invitations"
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "Invalid organization ID"
    finally:
        app.dependency_overrides.clear()


def test_admin_cannot_revoke_another_organizations_invitation():
    app.dependency_overrides[require_admin] = override_admin
    invitation_id = "11111111-1111-4111-8111-111111111111"

    try:
        response = client.post(
            f"/api/organizations/{OTHER_ORGANIZATION_ID}"
            f"/invitations/{invitation_id}/revoke"
        )

        assert response.status_code == 403
        assert response.json()["detail"] == (
            "Access denied for this organization"
        )
    finally:
        app.dependency_overrides.clear()


def test_invalid_invitation_id_returns_400():
    app.dependency_overrides[require_admin] = override_admin

    try:
        response = client.post(
            f"/api/organizations/{ORGANIZATION_ID}"
            "/invitations/not-a-valid-uuid/revoke"
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "Invalid invitation ID"
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------
# Day 14: Invitation acceptance lifecycle tests
# ---------------------------------------------------------

def test_accept_invitation_with_invalid_token_returns_400():
    mock_db = MagicMock()
    mock_db.execute.return_value.scalar_one_or_none.return_value = None
    setup_accept_invitation_test(mock_db)

    try:
        response = client.post(
            "/api/auth/accept-invitation",
            json={
                "token": "invalid-invitation-token-123",
                "name": "Test Member",
                "password": "StrongPassword123!",
            },
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "Invalid invitation"
        mock_db.rollback.assert_called_once()
        mock_db.commit.assert_not_called()
    finally:
        app.dependency_overrides.clear()


def test_accept_already_accepted_invitation_returns_400():
    invitation = make_mock_invitation(
        accepted_at=datetime.now(timezone.utc)
    )

    mock_db = MagicMock()
    mock_db.execute.return_value.scalar_one_or_none.return_value = invitation
    setup_accept_invitation_test(mock_db)

    try:
        response = client.post(
            "/api/auth/accept-invitation",
            json={
                "token": TEST_TOKEN,
                "name": "Test Member",
                "password": "StrongPassword123!",
            },
        )

        assert response.status_code == 400
        assert response.json()["detail"] == (
            "Invitation has already been accepted"
        )
        mock_db.rollback.assert_called_once()
        mock_db.commit.assert_not_called()
    finally:
        app.dependency_overrides.clear()


def test_accept_revoked_invitation_returns_400():
    invitation = make_mock_invitation(
        revoked_at=datetime.now(timezone.utc)
    )

    mock_db = MagicMock()
    mock_db.execute.return_value.scalar_one_or_none.return_value = invitation
    setup_accept_invitation_test(mock_db)

    try:
        response = client.post(
            "/api/auth/accept-invitation",
            json={
                "token": TEST_TOKEN,
                "name": "Test Member",
                "password": "StrongPassword123!",
            },
        )

        assert response.status_code == 400
        assert response.json()["detail"] == (
            "Invitation has been revoked"
        )
        mock_db.rollback.assert_called_once()
        mock_db.commit.assert_not_called()
    finally:
        app.dependency_overrides.clear()


def test_accept_expired_invitation_returns_400():
    invitation = make_mock_invitation(
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1)
    )

    mock_db = MagicMock()
    mock_db.execute.return_value.scalar_one_or_none.return_value = invitation
    setup_accept_invitation_test(mock_db)

    try:
        response = client.post(
            "/api/auth/accept-invitation",
            json={
                "token": TEST_TOKEN,
                "name": "Test Member",
                "password": "StrongPassword123!",
            },
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "Invitation has expired"
        mock_db.rollback.assert_called_once()
        mock_db.commit.assert_not_called()
    finally:
        app.dependency_overrides.clear()


def test_accept_invitation_rejects_existing_user():
    invitation = make_mock_invitation()
    existing_user = SimpleNamespace(
        id=UUID(MEMBER_ID),
        email=invitation.email,
    )

    mock_db = MagicMock()
    mock_db.execute.return_value.scalar_one_or_none.side_effect = [
        invitation,
        existing_user,
    ]
    setup_accept_invitation_test(mock_db)

    try:
        response = client.post(
            "/api/auth/accept-invitation",
            json={
                "token": TEST_TOKEN,
                "name": "Test Member",
                "password": "StrongPassword123!",
            },
        )

        assert response.status_code == 409
        assert response.json()["detail"] == (
            "An account with this email already exists"
        )
        mock_db.rollback.assert_called_once()
        mock_db.commit.assert_not_called()
    finally:
        app.dependency_overrides.clear()


def test_accept_invitation_creates_user_successfully():
    invitation = make_mock_invitation()

    mock_db = MagicMock()
    mock_db.execute.return_value.scalar_one_or_none.side_effect = [
        invitation,
        None,
    ]

    # Simulate SQLAlchemy assigning a primary key to the new user.
    def assign_user_id(user):
        if isinstance(user, User) and user.id is None:
            user.id = UUID("22222222-2222-4222-8222-222222222222")

    mock_db.add.side_effect = assign_user_id
    setup_accept_invitation_test(mock_db)

    try:
        response = client.post(
            "/api/auth/accept-invitation",
            json={
                "token": TEST_TOKEN,
                "name": "  Test Member  ",
                "password": "StrongPassword123!",
            },
        )

        assert response.status_code == 200
        data = response.json()

        assert data["message"] == (
            "Invitation accepted and account created successfully"
        )
        assert data["user"]["name"] == "Test Member"
        assert data["user"]["email"] == "newmember@example.com"
        assert data["user"]["role"] == "member"
        assert data["user"]["organization_id"] == ORGANIZATION_ID

        assert invitation.accepted_at is not None
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()
    finally:
        app.dependency_overrides.clear()
