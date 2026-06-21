from dataclasses import dataclass, field
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class DomainEvent:
    event: str
    occurred_at: str = field(default_factory=_now)


@dataclass
class EmployeeHired(DomainEvent):
    event: str = "employee.hired"
    employee_id: int = 0


@dataclass
class EmployeePromoted(DomainEvent):
    event: str = "employee.promoted"
    employee_id: int = 0
    old_role: str = ""
    new_role: str = ""


@dataclass
class ManagerAssigned(DomainEvent):
    event: str = "employee.manager_assigned"
    employee_id: int = 0
    manager_id: int = 0


@dataclass
class EmployeeActivated(DomainEvent):
    event: str = "employee.activated"
    employee_id: int = 0


@dataclass
class EmployeeDeactivated(DomainEvent):
    event: str = "employee.deactivated"
    employee_id: int = 0


@dataclass
class EmployeeAssignedToArea(DomainEvent):
    event: str = "employee.area_assigned"
    employee_id: int = 0
    area_id: int = 0


@dataclass
class AreaCreated(DomainEvent):
    event: str = "area.created"
    area_id: int = 0


@dataclass
class AreaUpdated(DomainEvent):
    event: str = "area.updated"
    area_id: int = 0


@dataclass
class AreaHeadAssigned(DomainEvent):
    event: str = "area.head_assigned"
    area_id: int = 0
    head_employee_id: int = 0


@dataclass
class AreaDeleted(DomainEvent):
    event: str = "area.deleted"
    area_id: int = 0
