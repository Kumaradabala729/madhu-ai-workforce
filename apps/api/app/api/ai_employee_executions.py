import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.core.security import require_admin
from datetime import datetime
from app.db.session import get_db
from app.models.ai_employee import AIEmployee
from app.models.ai_employee_execution import AIEmployeeExecution

from app.schemas.ai_employee_execution import (
    AIEmployeeExecutionCreateRequest,
)
from app.services.execution_service import (
    process_execution,
    retry_execution,
)

router = APIRouter(
    prefix="/api/organizations/{organization_id}/ai-employees/{employee_id}/executions",
    tags=["AI Employee Executions"],
)


def validate_organization_id(organization_id: str, current_user):
    try:
        organization_uuid = uuid.UUID(organization_id)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid organization ID",
        )

    if organization_uuid != current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this organization",
        )

    return organization_uuid


def validate_employee_id(employee_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(employee_id)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid AI employee ID",
        )


def validate_execution_id(execution_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(execution_id)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid execution ID",
        )


def get_active_employee(db, organization_uuid, employee_uuid):
    statement = select(AIEmployee).where(
        AIEmployee.id == employee_uuid,
        AIEmployee.organization_id == organization_uuid,
    )

    employee = db.execute(statement).scalar_one_or_none()

    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="AI employee not found",
        )

    if employee.status != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="AI employee must be active to execute tasks",
        )

    return employee


def serialize_execution(execution: AIEmployeeExecution) -> dict:
    return {
        "id": str(execution.id),
        "organization_id": str(execution.organization_id),
        "ai_employee_id": str(execution.ai_employee_id),
        "task": execution.task,
        "status": execution.status,
        "input_data": execution.input_data,
        "output_data": execution.output_data,
        "error_message": execution.error_message,
        "retry_count": execution.retry_count,
        "created_at": (
            execution.created_at.isoformat()
            if execution.created_at else None
        ),
        "updated_at": (
            execution.updated_at.isoformat()
            if execution.updated_at else None
        ),
    }


def get_execution(db, organization_uuid, employee_uuid, execution_uuid):
    statement = select(AIEmployeeExecution).where(
        AIEmployeeExecution.id == execution_uuid,
        AIEmployeeExecution.organization_id == organization_uuid,
        AIEmployeeExecution.ai_employee_id == employee_uuid,
    )

    execution = db.execute(statement).scalar_one_or_none()

    if execution is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Execution not found",
        )

    return execution
@router.post("", status_code=status.HTTP_201_CREATED)
def create_execution(
    organization_id: str,
    employee_id: str,
    request: AIEmployeeExecutionCreateRequest,
    current_user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    organization_uuid = validate_organization_id(
        organization_id, current_user
    )
    employee_uuid = validate_employee_id(employee_id)

    employee = get_active_employee(
        db, organization_uuid, employee_uuid
    )

    task = request.task.strip()

    if not task:
        raise HTTPException(
            status_code=422,
            detail="Task cannot be empty",
        )

    execution = AIEmployeeExecution(
        organization_id=organization_uuid,
        ai_employee_id=employee.id,
        task=task,
        status="pending",
        input_data=request.input_data,
    )

    try:
        db.add(execution)
        db.commit()
        db.refresh(execution)
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to create execution",
        )

    return {"execution": serialize_execution(execution)}

@router.get("")
def list_executions(
    organization_id: str,
    employee_id: str,
    status: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    search: Optional[str] = Query(default=None, min_length=1, max_length=200),
    sort_order: str = Query(default="newest"),
    retried_only: bool = Query(default=False),
    start_date: Optional[datetime] = Query(default=None),
    end_date: Optional[datetime] = Query(default=None),
    current_user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    organization_uuid = validate_organization_id(
        organization_id, current_user
    )
    employee_uuid = validate_employee_id(employee_id)

    allowed_statuses = {"pending", "running", "completed", "failed"}

    if status is not None and status not in allowed_statuses:
        raise HTTPException(
            status_code=422,
            detail="Invalid execution status",
        )
    if sort_order not in {"newest", "oldest"}:
        raise HTTPException(
            status_code=422,
            detail="Invalid sort order",
    )
    if (
        start_date is not None
        and end_date is not None
        and start_date > end_date
    ):
        raise HTTPException(
            status_code=422,
            detail="Start date must be before or equal to end date",
        )
    employee = get_active_employee(
        db, organization_uuid, employee_uuid
    )

    filters = [
        AIEmployeeExecution.organization_id == organization_uuid,
        AIEmployeeExecution.ai_employee_id == employee.id,
    ]

    if status is not None:
        filters.append(AIEmployeeExecution.status == status)
    if search is not None:
        filters.append(
            AIEmployeeExecution.task.ilike(f"%{search.strip()}%")
        )
    if start_date is not None:
        filters.append(
            AIEmployeeExecution.created_at >= start_date
        )

    if end_date is not None:
        filters.append(
            AIEmployeeExecution.created_at <= end_date
        )
    if retried_only:
        filters.append(
            AIEmployeeExecution.retry_count > 0
        )
    total = db.execute(
        select(func.count(AIEmployeeExecution.id)).where(*filters)
    ).scalar_one()

    query = (
        select(AIEmployeeExecution)
        .where(*filters)
        .order_by(
            AIEmployeeExecution.created_at.asc()
            if sort_order == "oldest"
            else AIEmployeeExecution.created_at.desc()
        )
        .offset((page - 1) * limit)
        .limit(limit)
    )

    executions = db.execute(query).scalars().all()

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": (total + limit - 1) // limit,
        "executions": [
            serialize_execution(execution)
            for execution in executions
        ],
    }


@router.get("/{execution_id}")
def retrieve_execution(
    organization_id: str,
    employee_id: str,
    execution_id: str,
    current_user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    organization_uuid = validate_organization_id(
        organization_id, current_user
    )
    employee_uuid = validate_employee_id(employee_id)
    execution_uuid = validate_execution_id(execution_id)

    execution = get_execution(
        db,
        organization_uuid,
        employee_uuid,
        execution_uuid,
    )

    return {"execution": serialize_execution(execution)}


@router.post("/{execution_id}/process")
def process_ai_employee_execution(
    organization_id: str,
    employee_id: str,
    execution_id: str,
    current_user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    organization_uuid = validate_organization_id(
        organization_id, current_user
    )
    employee_uuid = validate_employee_id(employee_id)
    execution_uuid = validate_execution_id(execution_id)

    execution = get_execution(
        db,
        organization_uuid,
        employee_uuid,
        execution_uuid,
    )

    try:
        processed_execution = process_execution(db, execution)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )

    return {
        "execution": serialize_execution(processed_execution)
    }
@router.post("/{execution_id}/retry")
def retry_ai_employee_execution(
    organization_id: str,
    employee_id: str,
    execution_id: str,
    current_user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    organization_uuid = validate_organization_id(
        organization_id, current_user
    )
    employee_uuid = validate_employee_id(employee_id)
    execution_uuid = validate_execution_id(execution_id)

    execution = get_execution(
        db,
        organization_uuid,
        employee_uuid,
        execution_uuid,
    )

    try:
        retried_execution = retry_execution(db, execution)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )

    return {
        "execution": serialize_execution(retried_execution)
    }
