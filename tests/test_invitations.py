from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from types import SimpleNamespace
from uuid import UUID

from fastapi.testclient import TestClient

from app.main import app
from app.core.security import get_current_user, require_admin


client = TestClient(app)

ORGANIZATION_ID = "efdfb6e6-0184-4ff6-9bbb-6a99a57b1fc8"


def override_admin():
    return SimpleNamespace(
        id=UUID("f00ccf60-0f09-47ba-ae67-2c7eb2b0d245"),
        organization_id=UUID(ORGANIZATION_ID),
        role="admin",
    )


def override_member():
    return SimpleNamespace(
        id=UUID("04d10d2d-c299-4799-96ef-3f0026f4a3fa"),
        organization_id=UUID(ORGANIZATION_ID),
        role="member",
    )


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

    from app.db.session import get_db
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

    from app.db.session import get_db
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

    other_organization_id = "9b84ee15-28a4-4ed3-9719-09af9038f451"

    try:
        response = client.get(
            f"/api/organizations/{other_organization_id}/invitations"
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

    other_organization_id = "9b84ee15-28a4-4ed3-9719-09af9038f451"
    invitation_id = "11111111-1111-4111-8111-111111111111"

    try:
        response = client.post(
            f"/api/organizations/{other_organization_id}"
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
