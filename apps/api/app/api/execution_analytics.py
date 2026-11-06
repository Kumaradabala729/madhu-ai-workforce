import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.security import require_admin
from app.db.session import get_db
from app.models.ai_employee import AIEmployee
from app.models.ai_employee_execution import AIEmployeeExecution


router = APIRouter(
    prefix="/api/organizations/{organization_id}/execution-analytics",
    tags=["Execution Analytics"],
)


@router.get("")
def get_execution_analytics(
    organization_id: str,
    current_user=Depends(require_admin),
    db: Session = Depends(get_db),
):
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

    statement = select(
        func.count(AIEmployeeExecution.id).label("total"),
        func.sum(
            case((AIEmployeeExecution.status == "pending", 1), else_=0)
        ).label("pending"),
        func.sum(
            case((AIEmployeeExecution.status == "running", 1), else_=0)
        ).label("running"),
        func.sum(
            case((AIEmployeeExecution.status == "completed", 1), else_=0)
        ).label("completed"),
        func.sum(
            case((AIEmployeeExecution.status == "failed", 1), else_=0)
        ).label("failed"),
        func.coalesce(
            func.sum(AIEmployeeExecution.retry_count), 0
        ).label("total_retries"),
    ).where(
        AIEmployeeExecution.organization_id == organization_uuid
    )

    result = db.execute(statement).one()

    total = result.total or 0
    completed = result.completed or 0
    failed = result.failed or 0

    success_rate = round((completed / total) * 100, 2) if total else 0
    failure_rate = round((failed / total) * 100, 2) if total else 0

    employee_statement = (
        select(
            AIEmployee.id.label("employee_id"),
            AIEmployee.name.label("employee_name"),
            func.count(AIEmployeeExecution.id).label("total"),
            func.sum(
                case(
                    (AIEmployeeExecution.status == "completed", 1),
                    else_=0,
                )
            ).label("completed"),
            func.sum(
                case(
                    (AIEmployeeExecution.status == "failed", 1),
                    else_=0,
                )
            ).label("failed"),
        )
        .outerjoin(
            AIEmployeeExecution,
            AIEmployeeExecution.ai_employee_id == AIEmployee.id,
        )
        .where(AIEmployee.organization_id == organization_uuid)
        .group_by(AIEmployee.id, AIEmployee.name)
        .order_by(AIEmployee.name)
    )

    employee_results = db.execute(employee_statement).all()

    return {
        "organization_id": str(organization_uuid),
        "summary": {
            "total_executions": total,
            "pending": result.pending or 0,
            "running": result.running or 0,
            "completed": completed,
            "failed": failed,
            "total_retries": result.total_retries or 0,
            "success_rate": success_rate,
            "failure_rate": failure_rate,
        },
        "employee_statistics": [
            {
                "employee_id": str(employee.employee_id),
                "employee_name": employee.employee_name,
                "total_executions": employee.total,
                "completed": employee.completed or 0,
                "failed": employee.failed or 0,
            }
            for employee in employee_results
        ],
    }