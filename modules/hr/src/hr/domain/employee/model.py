from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hr.db import Base

if TYPE_CHECKING:
    from hr.domain.area.model import Area

ROLE_ORDER = ["JUNIOR", "MID", "SENIOR", "LEAD", "MANAGER", "DIRECTOR"]
MIN_DAYS_IN_ROLE = 180
MIN_SALARY_INCREASE_PCT = 10.0
MAX_SALARY_INCREASE_PCT = 50.0
MIN_MANAGER_ROLE = "LEAD"


class Role(StrEnum):
    JUNIOR = "JUNIOR"
    MID = "MID"
    SENIOR = "SENIOR"
    LEAD = "LEAD"
    MANAGER = "MANAGER"
    DIRECTOR = "DIRECTOR"


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    role: Mapped[Role] = mapped_column(Enum(Role, native_enum=False, length=20))
    salary: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    hire_date: Mapped[date] = mapped_column(Date)
    role_since: Mapped[date] = mapped_column(Date)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    manager_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    # use_alter avoids circular DDL: employees → areas → employees
    area_id: Mapped[int | None] = mapped_column(
        ForeignKey("areas.id", use_alter=True, name="fk_emp_area")
    )

    manager: Mapped[Employee | None] = relationship(
        "Employee",
        foreign_keys="[Employee.manager_id]",
        back_populates="reports",
        remote_side="[Employee.id]",
    )
    reports: Mapped[list[Employee]] = relationship(
        "Employee",
        foreign_keys="[Employee.manager_id]",
        back_populates="manager",
    )
    area: Mapped[Area | None] = relationship(
        "Area",
        foreign_keys="[Employee.area_id]",
        back_populates="members",
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "role": self.role.value,
            "salary": float(self.salary),
            "hire_date": self.hire_date.isoformat(),
            "role_since": self.role_since.isoformat(),
            "active": self.active,
            "manager_id": self.manager_id,
            "area_id": self.area_id,
        }
