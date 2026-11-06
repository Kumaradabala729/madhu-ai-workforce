from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

from fastapi.testclient import TestClient

from app.main import app
from app.core.security import require_admin
from app.db.session import get_db
from app.services.execution_service import (
    process_execution,
    retry_execution,
)


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
        retry_count=0,
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

    employee_result = MagicMock()
    employee_result.scalar_one_or_none.return_value = employee

    count_result = MagicMock()
    count_result.scalar_one.return_value = 1

    execution_result = MagicMock()
    execution_result.scalars.return_value.all.return_value = [execution]

    mock_db.execute.side_effect = [
        employee_result,
        count_result,
        execution_result,
    ]

    setup_admin(mock_db)

    try:
        response = client.get(
            f"/api/organizations/{ORG_ID}/ai-employees/{EMPLOYEE_ID}/executions"
        )

        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 1
        assert data["page"] == 1
        assert data["limit"] == 20
        assert data["total_pages"] == 1
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

def test_process_execution_successfully():
    mock_db = MagicMock()
    execution = make_execution()

    result = process_execution(mock_db, execution)

    assert result.status == "completed"
    assert result.output_data["result"] == "Task processing completed"
    assert result.error_message is None
    assert mock_db.commit.call_count == 2
    assert mock_db.refresh.call_count == 2


def test_process_execution_rejects_non_pending_execution():
    mock_db = MagicMock()
    execution = make_execution()
    execution.status = "completed"

    try:
        process_execution(mock_db, execution)
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert str(exc) == "Only pending executions can be processed"

    mock_db.commit.assert_not_called()


def test_process_execution_marks_empty_task_as_failed():
    mock_db = MagicMock()
    execution = make_execution()
    execution.task = "   "

    result = process_execution(mock_db, execution)

    assert result.status == "failed"
    assert result.output_data is None
    assert result.error_message == "Execution task cannot be empty"
    mock_db.rollback.assert_called_once()
def test_retry_execution_successfully():
    mock_db = MagicMock()
    execution = make_execution()
    execution.status = "failed"
    execution.retry_count = 0
    execution.error_message = "Temporary failure"
    execution.output_data = {"old": "result"}

    result = retry_execution(mock_db, execution)

    assert result.status == "pending"
    assert result.retry_count == 1
    assert result.error_message is None
    assert result.output_data is None
    mock_db.commit.assert_called_once()
    mock_db.refresh.assert_called_once()


def test_retry_execution_rejects_non_failed_execution():
    mock_db = MagicMock()
    execution = make_execution()
    execution.status = "completed"

    try:
        retry_execution(mock_db, execution)
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert str(exc) == "Only failed executions can be retried"

    mock_db.commit.assert_not_called()


def test_retry_execution_rejects_maximum_retry_attempts():
    mock_db = MagicMock()
    execution = make_execution()
    execution.status = "failed"
    execution.retry_count = 3

    try:
        retry_execution(mock_db, execution)
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert str(exc) == "Maximum retry attempts reached"

    mock_db.commit.assert_not_called()
def test_list_executions_supports_pagination():
    mock_db = MagicMock()

    employee_result = MagicMock()
    employee_result.scalar_one_or_none.return_value = make_employee()

    count_result = MagicMock()
    count_result.scalar_one.return_value = 12

    execution_result = MagicMock()
    execution_result.scalars.return_value.all.return_value = [
        make_execution()
    ]

    mock_db.execute.side_effect = [
        employee_result,
        count_result,
        execution_result,
    ]

    setup_admin(mock_db)

    try:
        response = client.get(
            f"/api/organizations/{ORG_ID}/ai-employees/{EMPLOYEE_ID}/executions",
            params={"page": 2, "limit": 5},
        )

        assert response.status_code == 200

        data = response.json()

        assert data["total"] == 12
        assert data["page"] == 2
        assert data["limit"] == 5
        assert data["total_pages"] == 3
        assert len(data["executions"]) == 1
    finally:
        teardown()
def test_list_executions_rejects_invalid_pagination():
    setup_admin()

    try:
        url = (
            f"/api/organizations/{ORG_ID}/ai-employees/"
            f"{EMPLOYEE_ID}/executions"
        )

        invalid_params = [
            {"page": 0},
            {"limit": 0},
            {"limit": 101},
        ]

        for params in invalid_params:
            response = client.get(url, params=params)
            assert response.status_code == 422
    finally:
        teardown()
def test_list_executions_supports_task_search():
    mock_db = MagicMock()

    employee_result = MagicMock()
    employee_result.scalar_one_or_none.return_value = make_employee()

    count_result = MagicMock()
    count_result.scalar_one.return_value = 1

    execution_result = MagicMock()
    execution_result.scalars.return_value.all.return_value = [
        make_execution()
    ]

    mock_db.execute.side_effect = [
        employee_result,
        count_result,
        execution_result,
    ]

    setup_admin(mock_db)

    try:
        response = client.get(
            f"/api/organizations/{ORG_ID}/ai-employees/{EMPLOYEE_ID}/executions",
            params={"search": "student"},
        )

        assert response.status_code == 200

        data = response.json()
        assert data["total"] == 1
        assert len(data["executions"]) == 1
        assert data["executions"][0]["task"] == (
            "Follow up with a student"
        )
    finally:
        teardown()
