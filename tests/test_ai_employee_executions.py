from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

from fastapi.testclient import TestClient

from app.main import app
from app.core.security import require_admin
from app.db.session import get_db


client = TestClient(app)

ORG_ID = "efdfb6e6-0184-4ff6-9bbb-6a99a57b1fc8"
OTHER_ORG_ID = "9b84ee15-28a4-4ed3-9719-09af9038f451"
EMPLOYEE_ID = "11111111-1111-4111-8111-111111111111"
EXECUTION_ID = "22222222-2222-4222-8222-222222222222"


def override_admin():
    return SimpleNamespace(
        id=UUID("f00ccf60-0f09-47ba-ae67-2c7eb2b0d245"),
        organization_id=UUID(ORG_ID),
        role="admin",
    )


def make_employee(status="active", organization_id=ORG_ID):
    return SimpleNamespace(
        id=UUID(EMPLOYEE_ID),
        organization_id=UUID(organization_id),
        status=status,
    )


def make_execution():
    return SimpleNamespace(
        id=UUID(EXECUTION_ID),
        organization_id=UUID(ORG_ID),
        ai_employee_id=UUID(EMPLOYEE_ID),
        task="Follow up with a student",
        status="pending",
        input_data={"student": "Rahul"},
        output_data=None,
        error_message=None,
        created_at=None,
        updated_at=None,
    )


def setup_admin(mock_db=None):
    app.dependency_overrides[require_admin] = override_admin

    if mock_db is not None:
        app.dependency_overrides[get_db] = lambda: mock_db


def teardown():
    app.dependency_overrides.clear()


def test_create_execution_successfully():
    mock_db = MagicMock()
    employee = make_employee()
    execution = make_execution()

    mock_db.execute.return_value.scalar_one_or_none.return_value = employee

    def assign_execution_id(instance):
        instance.id = execution.id

    mock_db.add.side_effect = assign_execution_id
    mock_db.refresh.side_effect = lambda instance: None

    setup_admin(mock_db)

    try:
        response = client.post(
            f"/api/organizations/{ORG_ID}/ai-employees/{EMPLOYEE_ID}/executions",
            json={
                "task": "Follow up with a student",
                "input_data": {"student": "Rahul"},
            },
        )

        assert response.status_code == 201
        data = response.json()["execution"]

        assert data["task"] == "Follow up with a student"
        assert data["status"] == "pending"
        assert data["input_data"] == {"student": "Rahul"}

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()
    finally:
        teardown()


def test_create_execution_rejects_draft_employee():
    mock_db = MagicMock()
    mock_db.execute.return_value.scalar_one_or_none.return_value = (
        make_employee(status="draft")
    )
    setup_admin(mock_db)

    try:
        response = client.post(
            f"/api/organizations/{ORG_ID}/ai-employees/{EMPLOYEE_ID}/executions",
            json={"task": "Follow up with a student"},
        )

        assert response.status_code == 409
        assert response.json()["detail"] == (
            "AI employee must be active to execute tasks"
        )
        mock_db.add.assert_not_called()
    finally:
        teardown()


def test_create_execution_rejects_paused_employee():
    mock_db = MagicMock()
    mock_db.execute.return_value.scalar_one_or_none.return_value = (
        make_employee(status="paused")
    )
    setup_admin(mock_db)

    try:
        response = client.post(
            f"/api/organizations/{ORG_ID}/ai-employees/{EMPLOYEE_ID}/executions",
            json={"task": "Follow up with a student"},
        )

        assert response.status_code == 409
        mock_db.add.assert_not_called()
    finally:
        teardown()


def test_create_execution_rejects_empty_task():
    mock_db = MagicMock()
    mock_db.execute.return_value.scalar_one_or_none.return_value = (
        make_employee()
    )
    setup_admin(mock_db)

    try:
        response = client.post(
            f"/api/organizations/{ORG_ID}/ai-employees/{EMPLOYEE_ID}/executions",
            json={"task": "   "},
        )

        assert response.status_code == 422
        mock_db.add.assert_not_called()
    finally:
        teardown()


def test_create_execution_rejects_invalid_organization_id():
    setup_admin()

    try:
        response = client.post(
            f"/api/organizations/not-a-uuid/ai-employees/{EMPLOYEE_ID}/executions",
            json={"task": "Follow up"},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "Invalid organization ID"
    finally:
        teardown()


def test_create_execution_rejects_invalid_employee_id():
    setup_admin()

    try:
        response = client.post(
            f"/api/organizations/{ORG_ID}/ai-employees/not-a-uuid/executions",
            json={"task": "Follow up"},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "Invalid AI employee ID"
    finally:
        teardown()


def test_create_execution_returns_404_for_missing_employee():
    mock_db = MagicMock()
    mock_db.execute.return_value.scalar_one_or_none.return_value = None
    setup_admin(mock_db)

    try:
        response = client.post(
            f"/api/organizations/{ORG_ID}/ai-employees/{EMPLOYEE_ID}/executions",
            json={"task": "Follow up"},
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "AI employee not found"
        mock_db.add.assert_not_called()
    finally:
        teardown()


def test_admin_cannot_create_execution_for_another_organization():
    mock_db = MagicMock()
    setup_admin(mock_db)

    try:
        response = client.post(
            f"/api/organizations/{OTHER_ORG_ID}/ai-employees/{EMPLOYEE_ID}/executions",
            json={"task": "Follow up"},
        )

        assert response.status_code == 403
        mock_db.execute.assert_not_called()
    finally:
        teardown()


def test_list_executions_successfully():
    mock_db = MagicMock()
    employee = make_employee()
    execution = make_execution()

    mock_db.execute.return_value.scalar_one_or_none.return_value = employee
    mock_db.execute.return_value.scalars.return_value.all.return_value = [
        execution
    ]

    setup_admin(mock_db)

    try:
        response = client.get(
            f"/api/organizations/{ORG_ID}/ai-employees/{EMPLOYEE_ID}/executions"
        )

        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 1
        assert data["executions"][0]["task"] == (
            "Follow up with a student"
        )
    finally:
        teardown()


def test_retrieve_execution_successfully():
    mock_db = MagicMock()
    execution = make_execution()

    mock_db.execute.return_value.scalar_one_or_none.return_value = execution
    setup_admin(mock_db)

    try:
        response = client.get(
            f"/api/organizations/{ORG_ID}/ai-employees/{EMPLOYEE_ID}/executions/{EXECUTION_ID}"
        )

        assert response.status_code == 200
        assert response.json()["execution"]["status"] == "pending"
    finally:
        teardown()


def test_retrieve_execution_rejects_invalid_execution_id():
    setup_admin()

    try:
        response = client.get(
            f"/api/organizations/{ORG_ID}/ai-employees/{EMPLOYEE_ID}/executions/not-a-uuid"
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "Invalid execution ID"
    finally:
        teardown()


def test_retrieve_execution_returns_404_when_missing():
    mock_db = MagicMock()
    mock_db.execute.return_value.scalar_one_or_none.return_value = None
    setup_admin(mock_db)

    try:
        response = client.get(
            f"/api/organizations/{ORG_ID}/ai-employees/{EMPLOYEE_ID}/executions/{EXECUTION_ID}"
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Execution not found"
    finally:
        teardown()


def test_create_execution_rolls_back_on_database_failure():
    mock_db = MagicMock()
    mock_db.execute.return_value.scalar_one_or_none.return_value = (
        make_employee()
    )
    mock_db.commit.side_effect = Exception("Database failure")

    setup_admin(mock_db)

    try:
        response = client.post(
            f"/api/organizations/{ORG_ID}/ai-employees/{EMPLOYEE_ID}/executions",
            json={"task": "Follow up"},
        )

        assert response.status_code == 500
        assert response.json()["detail"] == "Failed to create execution"
        mock_db.rollback.assert_called_once()
    finally:
        teardown()