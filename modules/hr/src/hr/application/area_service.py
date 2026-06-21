from hr.domain.area.model import Area
from hr.domain.area.repository import AreaRepository
from hr.domain.area.commands import CreateAreaCommand, UpdateAreaCommand, AssignHeadCommand, DeleteAreaCommand
from hr.domain.employee.repository import EmployeeRepository
from hr.domain.employee.model import ROLE_ORDER, MIN_MANAGER_ROLE
from hr.domain.events import AreaCreated, AreaUpdated, AreaHeadAssigned, AreaDeleted
from hr.application.event_bus import EventBus
from hr.application.employee_service import HRError, NotFoundError, ConflictError


class AreaApplicationService:
    def __init__(
        self,
        area_repo: AreaRepository,
        employee_repo: EmployeeRepository,
        event_bus: EventBus,
    ):
        self._areas = area_repo
        self._employees = employee_repo
        self._bus = event_bus

    def create(self, cmd: CreateAreaCommand) -> Area:
        if self._areas.get_by_name(cmd.name):
            raise ConflictError(f"area '{cmd.name}' already exists")
        area = Area(name=cmd.name, description=cmd.description)
        self._areas.add(area)
        self._areas.commit()
        self._areas.refresh(area)
        self._bus.publish(AreaCreated(area_id=area.id))
        return area

    def list(self) -> list[Area]:
        return self._areas.list()

    def get(self, area_id: int) -> Area:
        area = self._areas.get(area_id)
        if area is None:
            raise NotFoundError("area", area_id)
        return area

    def update(self, cmd: UpdateAreaCommand) -> Area:
        area = self.get(cmd.area_id)
        if cmd.name and cmd.name != area.name:
            if self._areas.get_by_name(cmd.name):
                raise ConflictError(f"area '{cmd.name}' already exists")
            area.name = cmd.name
        if cmd.description is not None:
            area.description = cmd.description
        self._areas.commit()
        self._areas.refresh(area)
        self._bus.publish(AreaUpdated(area_id=area.id))
        return area

    def assign_head(self, cmd: AssignHeadCommand) -> Area:
        area = self.get(cmd.area_id)
        emp = self._employees.get(cmd.head_employee_id)
        if emp is None:
            raise NotFoundError("employee", cmd.head_employee_id)
        if not emp.active:
            raise HRError("cannot assign an inactive employee as area head")
        if ROLE_ORDER.index(emp.role.value) < ROLE_ORDER.index(MIN_MANAGER_ROLE):
            raise HRError(f"area head must be at {MIN_MANAGER_ROLE} level or above")
        area.head_employee_id = cmd.head_employee_id
        self._areas.commit()
        self._areas.refresh(area)
        self._bus.publish(AreaHeadAssigned(area_id=area.id, head_employee_id=cmd.head_employee_id))
        return area

    def get_members(self, area_id: int) -> list:
        self.get(area_id)
        return self._employees.list(area_id=area_id)

    def delete(self, cmd: DeleteAreaCommand) -> None:
        area = self.get(cmd.area_id)
        if self._areas.has_members(cmd.area_id):
            raise HRError("cannot delete an area that still has employees", 409)
        self._areas.delete(area)
        self._areas.commit()
        self._bus.publish(AreaDeleted(area_id=cmd.area_id))
