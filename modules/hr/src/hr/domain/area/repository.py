from __future__ import annotations

from sqlalchemy.orm import Session

from hr.domain.area.model import Area


class AreaRepository:
    def __init__(self, session: Session):
        self._db = session

    def add(self, area: Area) -> None:
        self._db.add(area)

    def get(self, area_id: int) -> Area | None:
        return self._db.get(Area, area_id)

    def get_by_name(self, name: str) -> Area | None:
        return self._db.query(Area).filter(Area.name == name).first()

    def list(self) -> list[Area]:
        return self._db.query(Area).order_by(Area.id).all()

    def has_members(self, area_id: int) -> bool:
        from hr.domain.employee.model import Employee

        return self._db.query(Employee).filter(Employee.area_id == area_id).count() > 0

    def delete(self, area: Area) -> None:
        self._db.delete(area)

    def commit(self) -> None:
        self._db.commit()

    def refresh(self, area: Area) -> None:
        self._db.refresh(area)
