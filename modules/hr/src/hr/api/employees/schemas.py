from datetime import date

from pydantic import BaseModel


class HireRequest(BaseModel):
    name: str
    email: str
    role: str
    salary: float
    area_id: int | None = None
    hire_date: date | None = None
    role_since: date | None = None


class PromoteRequest(BaseModel):
    salary_increase_pct: float


class AssignManagerRequest(BaseModel):
    manager_id: int


class AssignAreaRequest(BaseModel):
    area_id: int


class EmployeeFilters(BaseModel):
    area_id: int | None = None
    role: str | None = None
    active: bool | None = None
