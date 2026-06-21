from __future__ import annotations

from datetime import date

from hr.domain.employee.model import (
    Employee, Role, ROLE_ORDER,
    MIN_DAYS_IN_ROLE, MIN_SALARY_INCREASE_PCT, MAX_SALARY_INCREASE_PCT, MIN_MANAGER_ROLE,
)
from hr.domain.employee.repository import EmployeeRepository
from hr.domain.employee.commands import (
    HireCommand, PromoteCommand, AssignManagerCommand,
    ToggleStatusCommand, AssignAreaCommand, ListEmployeesCommand,
)
from hr.domain.area.repository import AreaRepository
from hr.domain.events import (
    EmployeeHired, EmployeePromoted, ManagerAssigned,
    EmployeeActivated, EmployeeDeactivated, EmployeeAssignedToArea,
)
from hr.application.event_bus import EventBus


class HRError(Exception):
    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


class NotFoundError(HRError):
    def __init__(self, entity: str, entity_id: int):
        super().__init__(f"{entity} {entity_id} not found", 404)


class ConflictError(HRError):
    def __init__(self, message: str):
        super().__init__(message, 409)


class EmployeeApplicationService:
    def __init__(
        self,
        employee_repo: EmployeeRepository,
        area_repo: AreaRepository,
        event_bus: EventBus,
    ):
        self._employees = employee_repo
        self._areas = area_repo
        self._bus = event_bus

    def hire(self, cmd: HireCommand) -> Employee:
        if cmd.salary <= 0:
            raise HRError("salary must be greater than 0", 400)
        if cmd.role not in ROLE_ORDER:
            raise HRError(f"invalid role '{cmd.role}'. Valid roles: {ROLE_ORDER}", 400)
        if self._employees.get_by_email(cmd.email):
            raise ConflictError(f"email '{cmd.email}' is already registered")
        if cmd.area_id is not None and self._areas.get(cmd.area_id) is None:
            raise NotFoundError("area", cmd.area_id)
        today = date.today()
        emp = Employee(
            name=cmd.name,
            email=cmd.email,
            role=Role(cmd.role),
            salary=cmd.salary,
            hire_date=cmd.hire_date or today,
            role_since=cmd.role_since or cmd.hire_date or today,
            area_id=cmd.area_id,
        )
        self._employees.add(emp)
        self._employees.commit()
        self._employees.refresh(emp)
        self._bus.publish(EmployeeHired(employee_id=emp.id))
        return emp

    def list(self, cmd: ListEmployeesCommand) -> list[Employee]:
        return self._employees.list(area_id=cmd.area_id, role=cmd.role, active=cmd.active)

    def get(self, employee_id: int) -> Employee:
        emp = self._employees.get(employee_id)
        if emp is None:
            raise NotFoundError("employee", employee_id)
        return emp

    def get_team(self, employee_id: int) -> list[Employee]:
        self.get(employee_id)
        return self._employees.list_direct_reports(employee_id)

    def promote(self, cmd: PromoteCommand) -> Employee:
        emp = self.get(cmd.employee_id)
        if not emp.active:
            raise HRError("cannot promote an inactive employee")
        days_in_role = (date.today() - emp.role_since).days
        if days_in_role < MIN_DAYS_IN_ROLE:
            raise HRError(
                f"employee must be in current role for at least {MIN_DAYS_IN_ROLE} days "
                f"(currently {days_in_role} days)"
            )
        current_idx = ROLE_ORDER.index(emp.role.value)
        if current_idx >= len(ROLE_ORDER) - 1:
            raise HRError("employee is already at the highest role (DIRECTOR)")
        if cmd.salary_increase_pct < MIN_SALARY_INCREASE_PCT:
            raise HRError(f"salary increase must be at least {MIN_SALARY_INCREASE_PCT:.0f}% for a promotion")
        if cmd.salary_increase_pct > MAX_SALARY_INCREASE_PCT:
            raise HRError(f"salary increase cannot exceed {MAX_SALARY_INCREASE_PCT:.0f}% for a promotion")
        old_role = emp.role.value
        emp.role = Role(ROLE_ORDER[current_idx + 1])
        emp.salary = float(emp.salary) * (1 + cmd.salary_increase_pct / 100)
        emp.role_since = date.today()
        self._employees.commit()
        self._employees.refresh(emp)
        self._bus.publish(EmployeePromoted(employee_id=emp.id, old_role=old_role, new_role=emp.role.value))
        self._bus.notify(subject="HR Notification", message=f"Promotion: {emp.name} is now {emp.role.value}")
        return emp

    def assign_manager(self, cmd: AssignManagerCommand) -> Employee:
        emp = self.get(cmd.employee_id)
        if cmd.employee_id == cmd.manager_id:
            raise HRError("an employee cannot manage themselves")
        manager = self.get(cmd.manager_id)
        if not manager.active:
            raise HRError("cannot assign an inactive employee as manager")
        if ROLE_ORDER.index(manager.role.value) < ROLE_ORDER.index(MIN_MANAGER_ROLE):
            raise HRError(f"manager must be at {MIN_MANAGER_ROLE} level or above")
        if self._employees.is_subordinate(cmd.manager_id, cmd.employee_id):
            raise HRError("circular reporting chain: manager is already a subordinate of this employee")
        emp.manager_id = cmd.manager_id
        self._employees.commit()
        self._employees.refresh(emp)
        self._bus.publish(ManagerAssigned(employee_id=emp.id, manager_id=cmd.manager_id))
        return emp

    def toggle_active(self, cmd: ToggleStatusCommand) -> Employee:
        emp = self.get(cmd.employee_id)
        if emp.active:
            active_reports = self._employees.count_active_reports(cmd.employee_id)
            if active_reports > 0:
                raise HRError(f"cannot deactivate employee who has {active_reports} active direct reports")
        emp.active = not emp.active
        self._employees.commit()
        self._employees.refresh(emp)
        event = EmployeeDeactivated(employee_id=emp.id) if not emp.active else EmployeeActivated(employee_id=emp.id)
        self._bus.publish(event)
        return emp

    def assign_area(self, cmd: AssignAreaCommand) -> Employee:
        emp = self.get(cmd.employee_id)
        if self._areas.get(cmd.area_id) is None:
            raise NotFoundError("area", cmd.area_id)
        emp.area_id = cmd.area_id
        self._employees.commit()
        self._employees.refresh(emp)
        self._bus.publish(EmployeeAssignedToArea(employee_id=emp.id, area_id=cmd.area_id))
        return emp
