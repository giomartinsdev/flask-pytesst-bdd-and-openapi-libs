from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass
class HireRequest:
    name: str
    email: str
    department: str
    role: str
    salary: float
    hire_date: Optional[date] = None
    role_since: Optional[date] = None


@dataclass
class PromoteRequest:
    salary_increase_pct: float


@dataclass
class AssignManagerRequest:
    manager_id: int


@dataclass
class EmployeeFilters:
    department: Optional[str] = None
    role: Optional[str] = None
    active: Optional[bool] = None
