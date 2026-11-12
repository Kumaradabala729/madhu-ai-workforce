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

def test_admin_cannot_retrieve_execution_from_another_organization():
    mock_db = MagicMock()
    setup_admin(mock_db)

    try:
        response = client.get(
            f"/api/organizations/{OTHER_ORG_ID}/ai-employees/{EMPLOYEE_ID}/executions/{EXECUTION_ID}"
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

        data = response.json()["execution"]

        assert data["id"] == EXECUTION_ID
        assert data["organization_id"] == ORG_ID
        assert data["ai_employee_id"] == EMPLOYEE_ID
        assert data["task"] == "Follow up with a student"
        assert data["status"] == "pending"
        assert data["input_data"] == {"student": "Rahul"}
        assert data["output_data"] is None
        assert data["error_message"] is None
        assert data["retry_count"] == 0
        assert data["created_at"] is None
        assert data["updated_at"] is None

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

def test_process_execution_handles_completion_database_failure():
    mock_db = MagicMock()
    execution = make_execution()

    mock_db.commit.side_effect = [
        None,
        Exception("Completion save failed"),
        None,
    ]

    result = process_execution(mock_db, execution)

    assert result.status == "failed"
    assert result.output_data is None
    assert result.error_message == "Completion save failed"
    assert mock_db.rollback.call_count == 1
    assert mock_db.commit.call_count == 3

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


def test_retry_execution_rolls_back_on_database_failure():
    mock_db = MagicMock()
    execution = make_execution()
    execution.status = "failed"
    execution.retry_count = 0

    mock_db.commit.side_effect = Exception("Database failure")

    try:
        retry_execution(mock_db, execution)
        assert False, "Expected database exception"
    except Exception as exc:
        assert str(exc) == "Database failure"

    mock_db.rollback.assert_called_once()

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
        assert response.json()["has_next"] is True
        assert response.json()["has_previous"] is True
        assert data["total_pages"] == 3
        assert len(data["executions"]) == 1
    finally:
        teardown()
def test_list_executions_returns_empty_results():
    mock_db = MagicMock()

    employee_result = MagicMock()
    employee_result.scalar_one_or_none.return_value = make_employee()

    count_result = MagicMock()
    count_result.scalar_one.return_value = 0

    execution_result = MagicMock()
    execution_result.scalars.return_value.all.return_value = []

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

        assert data["total"] == 0
        assert data["total_pages"] == 0
        assert data["executions"] == []
        assert data["has_next"] is False
        assert data["has_previous"] is False

    finally:
        teardown()
def test_list_executions_returns_empty_for_out_of_range_page():
    mock_db = MagicMock()

    employee_result = MagicMock()
    employee_result.scalar_one_or_none.return_value = make_employee()

    count_result = MagicMock()
    count_result.scalar_one.return_value = 12

    execution_result = MagicMock()
    execution_result.scalars.return_value.all.return_value = []

    mock_db.execute.side_effect = [
        employee_result,
        count_result,
        execution_result,
    ]

    setup_admin(mock_db)

    try:
        response = client.get(
            f"/api/organizations/{ORG_ID}/ai-employees/{EMPLOYEE_ID}/executions",
            params={"page": 5, "limit": 5},
        )

        assert response.status_code == 200

        data = response.json()

        assert data["total"] == 12
        assert data["page"] == 5
        assert data["total_pages"] == 3
        assert data["executions"] == []
        assert data["has_next"] is False
        assert data["has_previous"] is True

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
def test_list_executions_supports_date_range():
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
            params={
                "start_date": "2026-11-01T00:00:00",
                "end_date": "2026-11-07T23:59:59",
            },
        )

        assert response.status_code == 200
        assert response.json()["total"] == 1
    finally:
        teardown()
def test_list_executions_rejects_invalid_date_range():
    setup_admin()

    try:
        response = client.get(
            f"/api/organizations/{ORG_ID}/ai-employees/{EMPLOYEE_ID}/executions",
            params={
                "start_date": "2026-11-08T00:00:00",
                "end_date": "2026-11-07T00:00:00",
            },
        )

        assert response.status_code == 422
        assert response.json()["detail"] == (
            "Start date must be before or equal to end date"
        )
    finally:
        teardown()
def test_list_executions_supports_oldest_sorting():
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
            params={"sort_order": "oldest"},
        )

        assert response.status_code == 200
        assert response.json()["total"] == 1
    finally:
        teardown()
def test_list_executions_uses_stable_sorting():
    mock_db = MagicMock()

    employee_result = MagicMock()
    employee_result.scalar_one_or_none.return_value = make_employee()

    count_result = MagicMock()
    count_result.scalar_one.return_value = 2

    execution_result = MagicMock()
    execution_result.scalars.return_value.all.return_value = [
        make_execution(),
        make_execution(),
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
            params={"sort_order": "newest"},
        )

        assert response.status_code == 200

        executed_query = mock_db.execute.call_args_list[2].args[0]
        query_text = str(executed_query)

        assert "created_at DESC" in query_text
        assert "ai_employee_executions.id DESC" in query_text

    finally:
        teardown()
def test_list_executions_rejects_invalid_sort_order():
    setup_admin()

    try:
        response = client.get(
            f"/api/organizations/{ORG_ID}/ai-employees/{EMPLOYEE_ID}/executions",
            params={"sort_order": "random"},
        )

        assert response.status_code == 422
        assert response.json()["detail"] == "Invalid sort order"
    finally:
        teardown()
def test_list_executions_supports_retried_only_filter():
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
            params={"retried_only": "true"},
        )

        assert response.status_code == 200
        assert response.json()["total"] == 1

        executed_query = mock_db.execute.call_args_list[2][0][0]
        assert "retry_count" in str(executed_query)
    finally:
        teardown()
def test_list_executions_first_page_pagination_metadata():
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
            params={"page": 1, "limit": 5},
        )

        assert response.status_code == 200

        data = response.json()
        assert data["has_next"] is True
        assert data["has_previous"] is False
    finally:
        teardown()
def test_list_executions_last_page_pagination_metadata():
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
            params={"page": 3, "limit": 5},
        )

        assert response.status_code == 200

        data = response.json()
        assert data["total_pages"] == 3
        assert data["has_next"] is False
        assert data["has_previous"] is True
    finally:
        teardown()
def test_list_executions_supports_combined_filters():
    mock_db = MagicMock()

    employee_result = MagicMock()
    employee_result.scalar_one_or_none.return_value = make_employee()

    count_result = MagicMock()
    count_result.scalar_one.return_value = 1

    execution = make_execution()
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
            f"/api/organizations/{ORG_ID}/ai-employees/{EMPLOYEE_ID}/executions",
            params={
                "status": "completed",
                "search": "admission",
                "sort_order": "newest",
                "retried_only": True,
                "page": 1,
                "limit": 5,
                "start_date": "2026-01-01T00:00:00",
                "end_date": "2026-12-31T23:59:59",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["executions"]) == 1
        assert data["page"] == 1
        assert data["has_next"] is False
        assert data["has_previous"] is False

        executed_query = mock_db.execute.call_args_list[2].args[0]
        query_text = str(executed_query)

        assert "status" in query_text
        assert "retry_count" in query_text
        assert "LIKE" in query_text.upper()
        assert "created_at" in query_text
    finally:
        teardown()
def test_list_executions_rejects_incomplete_cursor():
    setup_admin()

    try:
        response = client.get(
            f"/api/organizations/{ORG_ID}/ai-employees/{EMPLOYEE_ID}/executions",
            params={
                "cursor_created_at": "2026-11-08T01:23:23+05:30",
            },
        )

        assert response.status_code == 422
        assert "Both cursor_created_at and cursor_id" in str(response.json())
    finally:
        teardown()
def test_list_executions_returns_next_cursor():
    from datetime import datetime, timezone

    mock_db = MagicMock()

    first_execution = make_execution()
    first_execution.created_at = datetime(
        2026, 11, 12, 10, 0, 0, tzinfo=timezone.utc
    )

    second_execution = make_execution()
    second_execution.id = UUID("af949e13-695e-4122-9ed1-373769655de6")
    second_execution.created_at = datetime(
        2026, 11, 12, 9, 0, 0, tzinfo=timezone.utc
    )

    employee_result = MagicMock()
    employee_result.scalar_one_or_none.return_value = make_employee()

    count_result = MagicMock()
    count_result.scalar_one.return_value = 10

    execution_result = MagicMock()
    execution_result.scalars.return_value.all.return_value = [
        first_execution,
        second_execution,
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
            params={"limit": 1},
        )

        assert response.status_code == 200

        data = response.json()
        assert data["has_next_cursor"] is True
        assert data["next_cursor"] is not None
        assert data["next_cursor"]["id"] == str(first_execution.id)
        assert len(data["executions"]) == 1
    finally:
        teardown()
def test_list_executions_uses_cursor_for_next_page():
    from datetime import datetime, timezone

    mock_db = MagicMock()

    next_execution = make_execution()
    next_execution.id = UUID("af949e13-695e-4122-9ed1-373769655de6")
    next_execution.created_at = datetime(
        2026, 11, 12, 9, 0, 0, tzinfo=timezone.utc
    )

    employee_result = MagicMock()
    employee_result.scalar_one_or_none.return_value = make_employee()

    count_result = MagicMock()
    count_result.scalar_one.return_value = 10

    execution_result = MagicMock()
    execution_result.scalars.return_value.all.return_value = [
        next_execution
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
            params={
                "limit": 1,
                "cursor_created_at": "2026-11-12T10:00:00+00:00",
                "cursor_id": EXECUTION_ID,
            },
        )

        assert response.status_code == 200

        data = response.json()
        assert len(data["executions"]) == 1
        assert data["executions"][0]["id"] == str(next_execution.id)
        assert data["has_next_cursor"] is False
        assert data["next_cursor"] is None
    finally:
        teardown()