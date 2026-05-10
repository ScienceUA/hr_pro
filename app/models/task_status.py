from typing import Any, Literal

from pydantic import BaseModel, Field


TaskStatusValue = Literal["pending", "running", "completed", "failed"]

TASK_STATUS_FIELDS = {
    "session_id",
    "status",
    "step",
    "progress",
    "message",
    "error",
    "report",
    "counters",
}


class TaskStatus(BaseModel):
    session_id: str
    status: TaskStatusValue
    step: str | None = None
    progress: str | None = None
    message: str | None = None
    error: str | None = None
    report: str | None = None
    counters: dict[str, Any] = Field(default_factory=dict)


def task_status_payload(
    session_id: str,
    status: TaskStatusValue,
    *,
    step: str | None = None,
    progress: str | None = None,
    message: str | None = None,
    error: str | None = None,
    report: str | None = None,
    counters: dict[str, Any] | None = None,
    **counter_values: Any,
) -> dict[str, Any]:
    merged_counters = dict(counters or {})
    merged_counters.update(counter_values)
    return TaskStatus(
        session_id=session_id,
        status=status,
        step=step,
        progress=progress,
        message=message,
        error=error,
        report=report,
        counters=merged_counters,
    ).model_dump()


def normalize_task_status(
    session_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    counters = dict(payload.get("counters") or {})
    for key, value in payload.items():
        if key not in TASK_STATUS_FIELDS:
            counters[key] = value

    return task_status_payload(
        session_id=session_id,
        status=payload.get("status", "failed"),
        step=payload.get("step"),
        progress=payload.get("progress"),
        message=payload.get("message"),
        error=payload.get("error"),
        report=payload.get("report"),
        counters=counters,
    )
