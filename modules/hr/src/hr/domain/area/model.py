from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from hr.db import Base


class Area(Base):
    __tablename__ = "areas"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, unique=True)
    description = Column(String(500), nullable=True)
    head_employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True)

    head = relationship(
        "Employee",
        foreign_keys="Area.head_employee_id",
        primaryjoin="Area.head_employee_id == Employee.id",
    )
    members = relationship(
        "Employee",
        foreign_keys="Employee.area_id",
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
