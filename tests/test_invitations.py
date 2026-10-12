
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
