from datetime import date

from pydantic import BaseModel


class HireCommand(BaseModel):
    name: str
    email: str
    role: str
    salary: float
    area_id: int | None = None
    hire_date: date | None = None
    role_since: date | None = None


class PromoteCommand(BaseModel):
    employee_id: int
    salary_increase_pct: float


class AssignManagerCommand(BaseModel):
    employee_id: int
    manager_id: int


class ToggleStatusCommand(BaseModel):
    employee_id: int


class AssignAreaCommand(BaseModel):
    employee_id: int
    area_id: int


class ListEmployeesCommand(BaseModel):
    area_id: int | None = None
    role: str | None = None
    active: bool | None = None
