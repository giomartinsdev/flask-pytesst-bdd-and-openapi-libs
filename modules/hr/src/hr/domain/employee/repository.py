from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from hr.domain.employee.model import Employee, Role


class EmployeeRepository:
    def __init__(self, session: Session):
        self._db = session

    def add(self, employee: Employee) -> None:
        self._db.add(employee)

    def get(self, employee_id: int) -> Optional[Employee]:
        return self._db.get(Employee, employee_id)

    def get_by_email(self, email: str) -> Optional[Employee]:
        return self._db.query(Employee).filter(Employee.email == email).first()

    def list(
        self,
        area_id: Optional[int] = None,
        role: Optional[str] = None,
        active: Optional[bool] = None,
    ) -> list[Employee]:
        q = self._db.query(Employee)
        if area_id is not None:
            q = q.filter(Employee.area_id == area_id)
        if role:
            q = q.filter(Employee.role == Role(role))
        if active is not None:
            q = q.filter(Employee.active == active)
        return q.order_by(Employee.id).all()

    def list_direct_reports(self, manager_id: int) -> list[Employee]:
        return self._db.query(Employee).filter(Employee.manager_id == manager_id).all()

    def count_active_reports(self, manager_id: int) -> int:
        return (
            self._db.query(Employee)
            .filter(Employee.manager_id == manager_id, Employee.active == True)
            .count()
        )

    def is_subordinate(self, candidate_id: int, root_id: int) -> bool:
        visited, queue = set(), [root_id]
        while queue:
            node = queue.pop()
            if node in visited:
                continue
            visited.add(node)
            for r in self._db.query(Employee).filter(Employee.manager_id == node).all():
                if r.id == candidate_id:
                    return True
                queue.append(r.id)
        return False

    def commit(self) -> None:
        self._db.commit()

    def refresh(self, employee: Employee) -> None:
        self._db.refresh(employee)
