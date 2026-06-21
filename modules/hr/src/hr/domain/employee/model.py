import enum

from sqlalchemy import Boolean, Column, Date, Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import relationship

from hr.db import Base

ROLE_ORDER = ["JUNIOR", "MID", "SENIOR", "LEAD", "MANAGER", "DIRECTOR"]
MIN_DAYS_IN_ROLE = 180
MIN_SALARY_INCREASE_PCT = 10.0
MAX_SALARY_INCREASE_PCT = 50.0
MIN_MANAGER_ROLE = "LEAD"


class Role(str, enum.Enum):
    JUNIOR = "JUNIOR"
    MID = "MID"
    SENIOR = "SENIOR"
    LEAD = "LEAD"
    MANAGER = "MANAGER"
    DIRECTOR = "DIRECTOR"


class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False, unique=True, index=True)
    role = Column(Enum(Role, native_enum=False, length=20), nullable=False)
    salary = Column(Numeric(12, 2), nullable=False)
    hire_date = Column(Date, nullable=False)
    role_since = Column(Date, nullable=False)
    active = Column(Boolean, nullable=False, default=True)
    manager_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    # use_alter avoids circular DDL: employees → areas → employees
    area_id = Column(Integer, ForeignKey("areas.id", use_alter=True, name="fk_emp_area"), nullable=True)

    manager = relationship(
        "Employee", foreign_keys=[manager_id],
        back_populates="reports", remote_side="Employee.id",
    )
    reports = relationship(
        "Employee", foreign_keys="Employee.manager_id", back_populates="manager",
    )
    area = relationship(
        "Area", foreign_keys="Employee.area_id", back_populates="members",
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
