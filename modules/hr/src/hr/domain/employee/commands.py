from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass
class HireCommand:
    name: str
    email: str
    role: str
    salary: float
    area_id: Optional[int] = None
    hire_date: Optional[date] = None
    role_since: Optional[date] = None


@dataclass
class PromoteCommand:
    employee_id: int
    salary_increase_pct: float


@dataclass
class AssignManagerCommand:
    employee_id: int
    manager_id: int


@dataclass
class ToggleStatusCommand:
    employee_id: int


@dataclass
class AssignAreaCommand:
    employee_id: int
    area_id: int


@dataclass
class ListEmployeesCommand:
    area_id: Optional[int] = None
    role: Optional[str] = None
    active: Optional[bool] = None
