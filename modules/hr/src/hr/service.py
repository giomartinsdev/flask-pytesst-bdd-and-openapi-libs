import json
from datetime import date

from sqlalchemy.orm import Session

from .models import (
    Employee, Role, ROLE_ORDER,
    MIN_DAYS_IN_ROLE, MIN_SALARY_INCREASE_PCT, MAX_SALARY_INCREASE_PCT, MIN_MANAGER_ROLE,
)
from .schemas import AssignManagerRequest, EmployeeFilters, HireRequest, PromoteRequest


class HRError(Exception):
    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


class NotFoundError(HRError):
    def __init__(self, eid: int):
        super().__init__(f"employee {eid} not found", 404)


class ConflictError(HRError):
    def __init__(self, message: str):
        super().__init__(message, 409)


class HRService:
    def __init__(self, session: Session, sqs_client=None, sns_client=None,
                 sqs_queue_url: str = "", sns_topic_arn: str = ""):
        self._db = session
        self._sqs = sqs_client
        self._sns = sns_client
        self._queue_url = sqs_queue_url
        self._topic_arn = sns_topic_arn

    def hire(self, req: HireRequest) -> Employee:
        if req.salary <= 0:
            raise HRError("salary must be greater than 0", 400)
        if req.role not in ROLE_ORDER:
            raise HRError(f"invalid role '{req.role}'. Valid roles: {ROLE_ORDER}", 400)
        if self._db.query(Employee).filter(Employee.email == req.email).first():
            raise ConflictError(f"email '{req.email}' is already registered")
        today = date.today()
        emp = Employee(
            name=req.name, email=req.email, department=req.department,
            role=Role(req.role), salary=req.salary,
            hire_date=req.hire_date or today,
            role_since=req.role_since or req.hire_date or today,
        )
        self._db.add(emp)
        self._db.commit()
        self._db.refresh(emp)
        self._publish("employee.hired", emp)
        return emp

    def list_employees(self, filters: EmployeeFilters) -> list:
        q = self._db.query(Employee)
        if filters.department:
            q = q.filter(Employee.department == filters.department)
        if filters.role:
            q = q.filter(Employee.role == Role(filters.role))
        if filters.active is not None:
            q = q.filter(Employee.active == filters.active)
        return q.order_by(Employee.id).all()

    def get(self, employee_id: int) -> Employee:
        emp = self._db.get(Employee, employee_id)
        if emp is None:
            raise NotFoundError(employee_id)
        return emp

    def get_team(self, employee_id: int) -> list:
        self.get(employee_id)
        return self._db.query(Employee).filter(Employee.manager_id == employee_id).all()

    def promote(self, employee_id: int, req: PromoteRequest) -> Employee:
        emp = self.get(employee_id)
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
        if req.salary_increase_pct < MIN_SALARY_INCREASE_PCT:
            raise HRError(f"salary increase must be at least {MIN_SALARY_INCREASE_PCT:.0f}% for a promotion")
        if req.salary_increase_pct > MAX_SALARY_INCREASE_PCT:
            raise HRError(f"salary increase cannot exceed {MAX_SALARY_INCREASE_PCT:.0f}% for a promotion")
        emp.role = Role(ROLE_ORDER[current_idx + 1])
        emp.salary = float(emp.salary) * (1 + req.salary_increase_pct / 100)
        emp.role_since = date.today()
        self._db.commit()
        self._db.refresh(emp)
        self._publish("employee.promoted", emp)
        self._notify(f"Promotion: {emp.name} is now {emp.role.value}")
        return emp

    def assign_manager(self, employee_id: int, req: AssignManagerRequest) -> Employee:
        emp = self.get(employee_id)
        if employee_id == req.manager_id:
            raise HRError("an employee cannot manage themselves")
        manager = self.get(req.manager_id)
        if not manager.active:
            raise HRError("cannot assign an inactive employee as manager")
        mgr_idx = ROLE_ORDER.index(manager.role.value)
        if mgr_idx < ROLE_ORDER.index(MIN_MANAGER_ROLE):
            raise HRError(f"manager must be at {MIN_MANAGER_ROLE} level or above")
        if self._is_subordinate(req.manager_id, employee_id):
            raise HRError("circular reporting chain: manager is already a subordinate of this employee")
        emp.manager_id = req.manager_id
        self._db.commit()
        self._db.refresh(emp)
        return emp

    def toggle_active(self, employee_id: int) -> Employee:
        emp = self.get(employee_id)
        if emp.active:
            active_reports = (
                self._db.query(Employee)
                .filter(Employee.manager_id == employee_id, Employee.active == True)
                .count()
            )
            if active_reports > 0:
                raise HRError(f"cannot deactivate employee who has {active_reports} active direct reports")
        emp.active = not emp.active
        self._db.commit()
        self._db.refresh(emp)
        return emp

    def _is_subordinate(self, candidate_id: int, root_id: int) -> bool:
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

    def _publish(self, event: str, emp: Employee) -> None:
        if self._sqs and self._queue_url:
            self._sqs.send_message(
                QueueUrl=self._queue_url,
                MessageBody=json.dumps({"event": event, "employee_id": emp.id}),
            )

    def _notify(self, message: str) -> None:
        if self._sns and self._topic_arn:
            self._sns.publish(TopicArn=self._topic_arn, Message=message, Subject="HR Notification")
