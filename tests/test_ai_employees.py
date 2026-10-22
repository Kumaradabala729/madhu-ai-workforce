
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

from fastapi.testclient import TestClient

from app.main import app
from app.core.security import get_current_user, require_admin
from app.db.session import get_db


client = TestClient(app)

ORG_ID = "efdfb6e6-0184-4ff6-9bbb-6a99a57b1fc8"
OTHER_ORG_ID = "9b84ee15-28a4-4ed3-9719-09af9038f451"
ADMIN_ID = "f00ccf60-0f09-47ba-ae67-2c7eb2b0d245"
EMPLOYEE_ID = "11111111-1111-4111-8111-111111111111"


def override_admin():
    return SimpleNamespace(
        id=UUID(ADMIN_ID),
        organization_id=UUID(ORG_ID),
        role="admin",
    )


def override_member():
    return SimpleNamespace(
        id=UUID("04d10d2d-c299-4799-96ef-3f0026f4a3fa"),
        organization_id=UUID(ORG_ID),
        role="member",
    )


def make_employee(
    employee_id=EMPLOYEE_ID,
    organization_id=ORG_ID,
    name="Maya",
    role="sales",
    description="AI sales employee",
    language="en",
    status="draft",
):
    return SimpleNamespace(
        id=UUID(employee_id),
        organization_id=UUID(organization_id),
        name=name,
        role=role,
        description=description,
        language=language,
        status=status,
    )


def setup_admin(mock_db=None):
    app.dependency_overrides[require_admin] = override_admin
    if mock_db is not None:
        app.dependency_overrides[get_db] = lambda: mock_db


def teardown():
    app.dependency_overrides.clear()


def test_create_ai_employee_successfully():
    mock_db = MagicMock()
    employee = make_employee()

    def assign_employee_id(instance):
        instance.id = employee.id
        instance.organization_id = UUID(ORG_ID)
        instance.status = "draft"

    mock_db.add.side_effect = assign_employee_id
    setup_admin(mock_db)

    try:
        response = client.post(
            f"/api/organizations/{ORG_ID}/ai-employees",
            json={
                "name": "Maya",
                "role": "sales",
                "description": "AI sales employee",
                "language": "en",
            },
        )

        assert response.status_code == 201
        data = response.json()["employee"]
        assert data["name"] == "Maya"
        assert data["role"] == "sales"
        assert data["status"] == "draft"
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()
    finally:
        teardown()


def test_create_ai_employee_rejects_invalid_organization_id():
    setup_admin()

    try:
        response = client.post(
            "/api/organizations/not-a-uuid/ai-employees",
            json={"name": "Maya"},
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "Invalid organization ID"
    finally:
        teardown()


def test_admin_cannot_create_employee_for_another_organization():
    setup_admin()

    try:
        response = client.post(
            f"/api/organizations/{OTHER_ORG_ID}/ai-employees",
            json={"name": "Maya"},
        )
        assert response.status_code == 403
    finally:
        teardown()


def test_member_cannot_manage_ai_employees():
    app.dependency_overrides[get_current_user] = override_member

    try:
        response = client.get(
            f"/api/organizations/{ORG_ID}/ai-employees"
        )
        assert response.status_code == 403
    finally:
        teardown()


def test_list_ai_employees_successfully():
    mock_db = MagicMock()
    mock_db.execute.return_value.scalars.return_value.all.return_value = [
        make_employee()
    ]
    setup_admin(mock_db)

    try:
        response = client.get(
            f"/api/organizations/{ORG_ID}/ai-employees"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["employees"][0]["name"] == "Maya"
    finally:
        teardown()


def test_get_ai_employee_successfully():
    mock_db = MagicMock()
    mock_db.execute.return_value.scalar_one_or_none.return_value = (
        make_employee()
    )
    setup_admin(mock_db)

    try:
        response = client.get(
            f"/api/organizations/{ORG_ID}/ai-employees/{EMPLOYEE_ID}"
        )

        assert response.status_code == 200
        assert response.json()["employee"]["name"] == "Maya"
    finally:
        teardown()


def test_get_ai_employee_rejects_invalid_employee_id():
    setup_admin()

    try:
        response = client.get(
            f"/api/organizations/{ORG_ID}/ai-employees/not-a-uuid"
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "Invalid AI employee ID"
    finally:
        teardown()


def test_get_ai_employee_returns_404_when_not_found():
    mock_db = MagicMock()
    mock_db.execute.return_value.scalar_one_or_none.return_value = None
    setup_admin(mock_db)

    try:
        response = client.get(
            f"/api/organizations/{ORG_ID}/ai-employees/{EMPLOYEE_ID}"
        )
        assert response.status_code == 404
        assert response.json()["detail"] == "AI employee not found"
    finally:
        teardown()


def test_admin_cannot_get_another_organizations_employee():
    mock_db = MagicMock()
    mock_db.execute.return_value.scalar_one_or_none.return_value = None
    setup_admin(mock_db)

    try:
        response = client.get(
            f"/api/organizations/{OTHER_ORG_ID}/ai-employees/{EMPLOYEE_ID}"
        )
        assert response.status_code == 403
        mock_db.execute.assert_not_called()
    finally:
        teardown()


def test_update_ai_employee_successfully():
    employee = make_employee()
    mock_db = MagicMock()
    mock_db.execute.return_value.scalar_one_or_none.return_value = employee
    setup_admin(mock_db)

    try:
        response = client.patch(
            f"/api/organizations/{ORG_ID}/ai-employees/{EMPLOYEE_ID}",
            json={"name": "Maya Sales", "status": "active"},
        )

        assert response.status_code == 200
        data = response.json()["employee"]
        assert data["name"] == "Maya Sales"
        assert data["status"] == "active"
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once_with(employee)
    finally:
        teardown()


def test_update_ai_employee_rejects_invalid_status():
    employee = make_employee()
    mock_db = MagicMock()
    mock_db.execute.return_value.scalar_one_or_none.return_value = employee
    setup_admin(mock_db)

    try:
        response = client.patch(
            f"/api/organizations/{ORG_ID}/ai-employees/{EMPLOYEE_ID}",
            json={"status": "running"},
        )
        assert response.status_code == 422
        mock_db.commit.assert_not_called()
    finally:
        teardown()


def test_create_ai_employee_rolls_back_on_database_failure():
    mock_db = MagicMock()
    mock_db.commit.side_effect = Exception("database failure")
    setup_admin(mock_db)

    try:
        response = client.post(
            f"/api/organizations/{ORG_ID}/ai-employees",
            json={"name": "Maya"},
        )

        assert response.status_code == 500
        assert response.json()["detail"] == "Failed to create AI employee"
        mock_db.rollback.assert_called_once()
    finally:
        teardown()


def test_update_ai_employee_rolls_back_on_database_failure():
    employee = make_employee()
    mock_db = MagicMock()
    mock_db.execute.return_value.scalar_one_or_none.return_value = employee
    mock_db.commit.side_effect = Exception("database failure")
    setup_admin(mock_db)

    try:
        response = client.patch(
            f"/api/organizations/{ORG_ID}/ai-employees/{EMPLOYEE_ID}",
            json={"name": "Maya Updated"},
        )

        assert response.status_code == 500
        assert response.json()["detail"] == "Failed to update AI employee"
        mock_db.rollback.assert_called_once()
    finally:
        teardown()
