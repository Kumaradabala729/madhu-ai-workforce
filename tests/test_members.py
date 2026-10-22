
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

from fastapi.testclient import TestClient

from app.main import app
from app.core.security import get_current_user, require_admin
from app.db.session import get_db
from app.models.user import User


client = TestClient(app)

ORG_ID = "efdfb6e6-0184-4ff6-9bbb-6a99a57b1fc8"
OTHER_ORG_ID = "9b84ee15-28a4-4ed3-9719-09af9038f451"
ADMIN_ID = "f00ccf60-0f09-47ba-ae67-2c7eb2b0d245"
MEMBER_ID = "04d10d2d-c299-4799-96ef-3f0026f4a3fa"
TARGET_MEMBER_ID = "11111111-1111-4111-8111-111111111111"


def override_admin():
    return SimpleNamespace(
        id=UUID(ADMIN_ID),
        organization_id=UUID(ORG_ID),
        role="admin",
    )


def override_member():
    return SimpleNamespace(
        id=UUID(MEMBER_ID),
        organization_id=UUID(ORG_ID),
        role="member",
    )


def setup_admin(mock_db=None):
    app.dependency_overrides[require_admin] = override_admin
    if mock_db is not None:
        app.dependency_overrides[get_db] = lambda: mock_db


def make_member(
    member_id=TARGET_MEMBER_ID,
    organization_id=ORG_ID,
    name="Test Member",
    email="member@example.com",
    role="member",
):
    return SimpleNamespace(
        id=UUID(member_id),
        organization_id=UUID(organization_id),
        name=name,
        email=email,
        role=role,
    )


def teardown():
    app.dependency_overrides.clear()



def test_list_members_returns_members_and_total():
    mock_db = MagicMock()

    # First query: total matching members.
    # Second query: members for the requested page.
    mock_db.execute.side_effect = [
        MagicMock(scalar_one=lambda: 1, scalar_one_or_none=lambda: 1),
        MagicMock(
            scalars=MagicMock(
                return_value=MagicMock(
                    all=MagicMock(return_value=[make_member()])
                )
            )
        ),
    ]

    setup_admin(mock_db)

    try:
        response = client.get(
            f"/api/organizations/{ORG_ID}/members"
        )

        assert response.status_code == 200

        data = response.json()
        assert data["total"] == 1
        assert data["page"] == 1
        assert data["page_size"] == 10
        assert data["total_pages"] == 1
        assert len(data["members"]) == 1
        assert data["members"][0]["name"] == "Test Member"
        assert data["members"][0]["email"] == "member@example.com"
        assert data["members"][0]["role"] == "member"

    finally:
        teardown()



def test_list_members_rejects_invalid_organization_id():
    setup_admin()

    try:
        response = client.get(
            "/api/organizations/not-a-uuid/members"
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "Invalid organization ID"
    finally:
        teardown()


def test_admin_cannot_list_another_organizations_members():
    setup_admin()

    try:
        response = client.get(
            f"/api/organizations/{OTHER_ORG_ID}/members"
        )
        assert response.status_code == 403
        assert response.json()["detail"] == (
            "Access denied for this organization"
        )
    finally:
        teardown()


def test_member_cannot_access_member_management():
    app.dependency_overrides[get_current_user] = override_member

    try:
        response = client.get(f"/api/organizations/{ORG_ID}/members")
        assert response.status_code == 403
    finally:
        teardown()


def test_update_member_role_successfully():
    target = make_member()
    mock_db = MagicMock()
    mock_db.execute.return_value.scalar_one_or_none.return_value = target
    setup_admin(mock_db)

    try:
        response = client.patch(
            f"/api/organizations/{ORG_ID}/members/{TARGET_MEMBER_ID}/role",
            json={"role": "admin"},
        )

        assert response.status_code == 200
        assert response.json()["member"]["role"] == "admin"
        assert target.role == "admin"
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once_with(target)
    finally:
        teardown()


def test_update_member_role_rejects_invalid_role():
    setup_admin()

    try:
        response = client.patch(
            f"/api/organizations/{ORG_ID}/members/{TARGET_MEMBER_ID}/role",
            json={"role": "owner"},
        )

        assert response.status_code == 422
    finally:
        teardown()


def test_update_member_role_rejects_invalid_member_id():
    setup_admin()

    try:
        response = client.patch(
            f"/api/organizations/{ORG_ID}/members/not-a-uuid/role",
            json={"role": "member"},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "Invalid member ID"
    finally:
        teardown()


def test_update_member_role_returns_404_when_member_not_found():
    mock_db = MagicMock()
    mock_db.execute.return_value.scalar_one_or_none.return_value = None
    setup_admin(mock_db)

    try:
        response = client.patch(
            f"/api/organizations/{ORG_ID}/members/{TARGET_MEMBER_ID}/role",
            json={"role": "admin"},
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Member not found"
    finally:
        teardown()


def test_admin_cannot_update_another_organizations_members():
    setup_admin()

    try:
        response = client.patch(
            f"/api/organizations/{OTHER_ORG_ID}/members/{TARGET_MEMBER_ID}/role",
            json={"role": "admin"},
        )

        assert response.status_code == 403
        assert response.json()["detail"] == (
            "Access denied for this organization"
        )
    finally:
        teardown()


def test_admin_cannot_remove_own_admin_role():
    admin = override_admin()
    mock_db = MagicMock()
    mock_db.execute.return_value.scalar_one_or_none.return_value = admin

    setup_admin(mock_db)

    try:
        response = client.patch(
            f"/api/organizations/{ORG_ID}/members/{ADMIN_ID}/role",
            json={"role": "member"},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == (
            "You cannot remove your own admin role"
        )
        mock_db.commit.assert_not_called()
    finally:
        teardown()

def test_list_members_returns_pagination_metadata():
    mock_db = MagicMock()
    mock_db.execute.side_effect = [
        MagicMock(scalar_one=lambda: 25),
        MagicMock(
            scalars=MagicMock(
                return_value=MagicMock(all=MagicMock(return_value=[]))
            )
        ),
    ]
    setup_admin(mock_db)

    try:
        response = client.get(
            f"/api/organizations/{ORG_ID}/members?page=2&page_size=10"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 25
        assert data["page"] == 2
        assert data["page_size"] == 10
        assert data["total_pages"] == 3
        assert data["members"] == []
    finally:
        teardown()


def test_list_members_rejects_invalid_page():
    setup_admin()

    try:
        response = client.get(
            f"/api/organizations/{ORG_ID}/members?page=0"
        )
        assert response.status_code == 422
    finally:
        teardown()


def test_list_members_rejects_page_size_over_100():
    setup_admin()

    try:
        response = client.get(
            f"/api/organizations/{ORG_ID}/members?page_size=101"
        )
        assert response.status_code == 422
    finally:
        teardown()

def test_list_members_search_returns_matching_members():
    matching_member = make_member(
        name="Kumar Adabala",
        email="kumar@example.com",
    )

    mock_db = MagicMock()
    mock_db.execute.side_effect = [
        MagicMock(scalar_one=lambda: 1),
        MagicMock(
            scalars=MagicMock(
                return_value=MagicMock(
                    all=MagicMock(return_value=[matching_member])
                )
            )
        ),
    ]

    setup_admin(mock_db)

    try:
        response = client.get(
            f"/api/organizations/{ORG_ID}/members?search=Kumar"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["members"]) == 1
        assert data["members"][0]["name"] == "Kumar Adabala"
    finally:
        teardown()


def test_list_members_search_returns_empty_when_no_matches():
    mock_db = MagicMock()
    mock_db.execute.side_effect = [
        MagicMock(scalar_one=lambda: 0),
        MagicMock(
            scalars=MagicMock(
                return_value=MagicMock(
                    all=MagicMock(return_value=[])
                )
            )
        ),
    ]

    setup_admin(mock_db)

    try:
        response = client.get(
            f"/api/organizations/{ORG_ID}/members?search=notfound"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["members"] == []
        assert data["total_pages"] == 0
    finally:
        teardown()

def test_list_members_rejects_search_longer_than_200_characters():
    setup_admin()

    try:
        response = client.get(
            f"/api/organizations/{ORG_ID}/members",
            params={"search": "a" * 201},
        )

        assert response.status_code == 422
    finally:
        teardown()
