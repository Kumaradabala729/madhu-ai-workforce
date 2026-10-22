
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import require_admin
from app.db.session import get_db
from app.models.ai_employee import AIEmployee
from app.schemas.ai_employee import (
    AIEmployeeCreateRequest,
    AIEmployeeUpdateRequest,
)

router = APIRouter(
    prefix="/api/organizations/{organization_id}/ai-employees",
    tags=["AI Employees"],
)


def validate_organization_id(organization_id: str, current_user):
    """Validate organization ID and enforce tenant isolation."""
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
    """Validate an AI employee UUID."""
    try:
        return uuid.UUID(employee_id)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid AI employee ID",
        )


def serialize_employee(employee: AIEmployee) -> dict:
    """Serialize an AI employee for API responses."""
    return {
        "id": str(employee.id),
        "organization_id": str(employee.organization_id),
        "name": employee.name,
        "role": employee.role,
        "description": employee.description,
        "language": employee.language,
        "status": employee.status,
    }


def get_employee(
    db: Session,
    organization_uuid: uuid.UUID,
    employee_uuid: uuid.UUID,
) -> AIEmployee:
    """Retrieve an employee within the specified organization."""
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

    return employee


@router.post("", status_code=status.HTTP_201_CREATED)
def create_ai_employee(
    organization_id: str,
    request: AIEmployeeCreateRequest,
    current_user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Create a draft AI employee."""
    organization_uuid = validate_organization_id(
        organization_id, current_user
    )

    name = request.name.strip()
    role = request.role.strip()
    language = request.language.strip()

    if not name:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Name cannot be empty",
        )

    if not role:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Role cannot be empty",
        )

    if not language:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Language cannot be empty",
        )

    description = (
        request.description.strip()
        if request.description is not None
        else None
    )

    employee = AIEmployee(
        organization_id=organization_uuid,
        name=name,
        role=role,
        description=description,
        language=language,
        status="draft",
    )

    try:
        db.add(employee)
        db.commit()
        db.refresh(employee)
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create AI employee",
        )

    return {"employee": serialize_employee(employee)}


@router.get("")
def list_ai_employees(
    organization_id: str,
    current_user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """List AI employees belonging to the current organization."""
    organization_uuid = validate_organization_id(
        organization_id, current_user
    )

    statement = (
        select(AIEmployee)
        .where(AIEmployee.organization_id == organization_uuid)
        .order_by(AIEmployee.name, AIEmployee.id)
    )

    employees = db.execute(statement).scalars().all()
    serialized_employees = [
        serialize_employee(employee) for employee in employees
    ]

    return {
        "total": len(serialized_employees),
        "employees": serialized_employees,
    }


@router.get("/{employee_id}")
def retrieve_ai_employee(
    organization_id: str,
    employee_id: str,
    current_user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Retrieve one AI employee."""
    organization_uuid = validate_organization_id(
        organization_id, current_user
    )
    employee_uuid = validate_employee_id(employee_id)

    employee = get_employee(
        db, organization_uuid, employee_uuid
    )

    return {"employee": serialize_employee(employee)}


@router.patch("/{employee_id}")
def update_ai_employee(
    organization_id: str,
    employee_id: str,
    request: AIEmployeeUpdateRequest,
    current_user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Update an AI employee's configuration."""
    organization_uuid = validate_organization_id(
        organization_id, current_user
    )
    employee_uuid = validate_employee_id(employee_id)

    employee = get_employee(
        db, organization_uuid, employee_uuid
    )

    # Pydantic v2: update only explicitly provided fields.
    updates = request.model_dump(exclude_unset=True)

    if not updates:
        return {"employee": serialize_employee(employee)}

    if "status" in updates:
        allowed_statuses = {"draft", "active", "paused"}

        if updates["status"] not in allowed_statuses:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    "Invalid status. Allowed values: "
                    "draft, active, paused"
                ),
            )

    for field in ("name", "role", "language"):
        if field in updates:
            value = updates[field]

            if value is None or not value.strip():
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=f"{field.capitalize()} cannot be empty",
                )

            updates[field] = value.strip()

    if "description" in updates:
        if updates["description"] is not None:
            updates["description"] = updates["description"].strip()

    try:
        for field, value in updates.items():
            setattr(employee, field, value)

        db.commit()
        db.refresh(employee)
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update AI employee",
        )

    return {"employee": serialize_employee(employee)}
