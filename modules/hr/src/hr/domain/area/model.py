from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hr.db import Base

if TYPE_CHECKING:
    from hr.domain.employee.model import Employee


class Area(Base):
    __tablename__ = "areas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    description: Mapped[str | None] = mapped_column(String(500))
    head_employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))

    head: Mapped[Employee | None] = relationship(
        "Employee",
        foreign_keys="[Area.head_employee_id]",
        primaryjoin="Area.head_employee_id == Employee.id",
    )
    members: Mapped[list[Employee]] = relationship(
        "Employee",
        foreign_keys="[Employee.area_id]",
        back_populates="area",
        primaryjoin="Area.id == Employee.area_id",
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "head_employee_id": self.head_employee_id,
        }
