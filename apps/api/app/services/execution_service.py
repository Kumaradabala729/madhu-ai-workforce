
from sqlalchemy.orm import Session

from app.models.ai_employee_execution import AIEmployeeExecution


def process_execution(
    db: Session,
    execution: AIEmployeeExecution,
) -> AIEmployeeExecution:
    """
    Process a pending AI employee execution.

    This is a rule-based processor for the initial MADHU
    execution engine. LLM integration will be added later.
    """

    if execution.status != "pending":
        raise ValueError(
            "Only pending executions can be processed"
        )

    try:
        execution.status = "running"
        execution.error_message = None
        db.commit()
        db.refresh(execution)

        task = execution.task.strip()

        if not task:
            raise ValueError("Execution task cannot be empty")

        output = {
            "message": "Task received and processed successfully",
            "task": task,
            "employee_id": str(execution.ai_employee_id),
            "result": "Task processing completed",
        }

        execution.output_data = output
        execution.status = "completed"
        execution.error_message = None

        db.commit()
        db.refresh(execution)

        return execution

    except Exception as exc:
        db.rollback()

        execution.status = "failed"
        execution.error_message = str(exc)
        execution.output_data = None

        try:
            db.commit()
            db.refresh(execution)
        except Exception:
            db.rollback()
            raise

        return execution
MAX_RETRY_ATTEMPTS = 3


def retry_execution(
    db: Session,
    execution: AIEmployeeExecution,
) -> AIEmployeeExecution:
    """Reset a failed execution for another processing attempt."""

    if execution.status != "failed":
        raise ValueError("Only failed executions can be retried")

    if execution.retry_count >= MAX_RETRY_ATTEMPTS:
        raise ValueError("Maximum retry attempts reached")

    try:
        execution.retry_count += 1
        execution.status = "pending"
        execution.error_message = None
        execution.output_data = None

        db.commit()
        db.refresh(execution)

        return execution

    except Exception:
        db.rollback()
        raise