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


def override_admin():
    return SimpleNamespace(
        id=UUID("f00ccf60-0f09-47ba-ae67-2c7eb2b0d245"),
        organization_id=UUID(ORG_ID),
        role="admin",
    )


def setup_admin(mock_db=None):
    app.dependency_overrides[require_admin] = override_admin

    if mock_db is not None:
        app.dependency_overrides[get_db] = lambda: mock_db


def teardown():
    app.dependency_overrides.clear()


def test_execution_analytics_returns_correct_statistics():
    mock_db = MagicMock()

    summary = SimpleNamespace(
        total=4,
        pending=1,
        running=0,
        completed=2,
        failed=1,
        total_retries=3,
    )

    employees = [
        SimpleNamespace(
            employee_id=UUID("11111111-1111-4111-8111-111111111111"),
            employee_name="Admissions Assistant",
            total=4,
            completed=2,
            failed=1,
        )
    ]

    mock_db.execute.side_effect = [
        SimpleNamespace(one=lambda: summary),
        SimpleNamespace(all=lambda: employees),
    ]

    setup_admin(mock_db)

    try:
        response = client.get(
            f"/api/organizations/{ORG_ID}/execution-analytics"
        )

        assert response.status_code == 200

        data = response.json()
        result = data["summary"]

        assert result["total_executions"] == 4
        assert result["pending"] == 1
        assert result["running"] == 0
        assert result["completed"] == 2
        assert result["failed"] == 1
        assert result["total_retries"] == 3
        assert result["success_rate"] == 50.0
        assert result["failure_rate"] == 25.0

        assert len(data["employee_statistics"]) == 1
        assert data["employee_statistics"][0]["employee_name"] == (
            "Admissions Assistant"
        )
    finally:
        teardown()


def test_execution_analytics_handles_empty_data():
    mock_db = MagicMock()

    summary = SimpleNamespace(
        total=0,
        pending=None,
        running=None,
        completed=None,
        failed=None,
        total_retries=0,
    )

    mock_db.execute.side_effect = [
        SimpleNamespace(one=lambda: summary),
        SimpleNamespace(all=lambda: []),
    ]

    setup_admin(mock_db)

    try:
        response = client.get(
            f"/api/organizations/{ORG_ID}/execution-analytics"
        )

        assert response.status_code == 200

        result = response.json()["summary"]

        assert result["total_executions"] == 0
        assert result["success_rate"] == 0
        assert result["failure_rate"] == 0
        assert result["total_retries"] == 0
        assert response.json()["employee_statistics"] == []
    finally:
        teardown()


def test_execution_analytics_rejects_invalid_organization_id():
    mock_db = MagicMock()
    setup_admin(mock_db)

    try:
        response = client.get(
            "/api/organizations/invalid-id/execution-analytics"
        )

        assert response.status_code == 400
        mock_db.execute.assert_not_called()
    finally:
        teardown()


def test_execution_analytics_rejects_another_organization():
    mock_db = MagicMock()
    setup_admin(mock_db)

    try:
        response = client.get(
            f"/api/organizations/{OTHER_ORG_ID}/execution-analytics"
        )

        assert response.status_code == 403
        mock_db.execute.assert_not_called()
    finally:
        teardown()
