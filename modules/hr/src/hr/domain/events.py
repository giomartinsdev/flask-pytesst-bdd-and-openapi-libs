from datetime import UTC, datetime

from pydantic import BaseModel, Field


def _now() -> str:
    return datetime.now(UTC).isoformat()


class DomainEvent(BaseModel):
    event: str
    occurred_at: str = Field(default_factory=_now)


class EmployeeHired(DomainEvent):
    event: str = "employee.hired"
    employee_id: int = 0


class EmployeePromoted(DomainEvent):
    event: str = "employee.promoted"
    employee_id: int = 0
    old_role: str = ""
    new_role: str = ""


class ManagerAssigned(DomainEvent):
    event: str = "employee.manager_assigned"
    employee_id: int = 0
    manager_id: int = 0


class EmployeeActivated(DomainEvent):
    event: str = "employee.activated"
    employee_id: int = 0


class EmployeeDeactivated(DomainEvent):
    event: str = "employee.deactivated"
    employee_id: int = 0


class EmployeeAssignedToArea(DomainEvent):
    event: str = "employee.area_assigned"
    employee_id: int = 0
    area_id: int = 0


class AreaCreated(DomainEvent):
    event: str = "area.created"
    area_id: int = 0


class AreaUpdated(DomainEvent):
    event: str = "area.updated"
    area_id: int = 0


class AreaHeadAssigned(DomainEvent):
    event: str = "area.head_assigned"
    area_id: int = 0
    head_employee_id: int = 0


class AreaDeleted(DomainEvent):
    event: str = "area.deleted"
    area_id: int = 0
