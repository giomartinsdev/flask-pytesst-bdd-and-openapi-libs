import os

import boto3
from flask import Blueprint, current_app, jsonify, request
from sqlalchemy.orm import Session

from hr.api.employees.schemas import (
    AssignAreaRequest,
    AssignManagerRequest,
    EmployeeFilters,
    HireRequest,
    PromoteRequest,
)
from hr.application.employee_service import EmployeeApplicationService, HRError
from hr.application.event_bus import EventBus
from hr.domain.area.repository import AreaRepository
from hr.domain.employee.commands import (
    AssignAreaCommand,
    AssignManagerCommand,
    HireCommand,
    ListEmployeesCommand,
    PromoteCommand,
    ToggleStatusCommand,
)
from hr.domain.employee.model import Employee
from hr.domain.employee.repository import EmployeeRepository
from lib.openapi import schema

employees_bp = Blueprint("employees", __name__, url_prefix="/employees")


def _make_service() -> EmployeeApplicationService:
    session: Session = current_app.config["SESSION_FACTORY"]()
    ep = os.environ.get("AWS_ENDPOINT_URL")
    bus = EventBus(
        sqs_client=boto3.client("sqs", endpoint_url=ep, region_name="us-east-1"),
        sns_client=boto3.client("sns", endpoint_url=ep, region_name="us-east-1"),
        queue_url=os.environ.get("HR_QUEUE_URL", ""),
        topic_arn=os.environ.get("HR_TOPIC_ARN", ""),
    )
    return EmployeeApplicationService(
        employee_repo=EmployeeRepository(session),
        area_repo=AreaRepository(session),
        event_bus=bus,
    )


def _err(msg: str, status: int):
    return jsonify({"error": msg}), status


@employees_bp.post("")
@schema(request=HireRequest, response=Employee, status=201)
def hire():
    data = request.get_json(silent=True) or {}
    missing = [f for f in ("name", "email", "role", "salary") if f not in data]
    if missing:
        return _err(f"missing fields: {', '.join(missing)}", 400)
    from datetime import date

    def _parse_date(v):
        return date.fromisoformat(v) if v else None

    svc = _make_service()
    try:
        emp = svc.hire(
            HireCommand(
                name=data["name"],
                email=data["email"],
                role=data["role"],
                salary=data["salary"],
                area_id=data.get("area_id"),
                hire_date=_parse_date(data.get("hire_date")),
                role_since=_parse_date(data.get("role_since")),
            )
        )
    except HRError as e:
        return _err(str(e), e.status)
    return jsonify(emp.to_dict()), 201


@employees_bp.get("")
@schema(query=EmployeeFilters, response=Employee, many=True)
def list_employees():
    active_param = request.args.get("active")
    active = None if active_param is None else active_param.lower() == "true"
    area_id_raw = request.args.get("area_id")
    area_id = int(area_id_raw) if area_id_raw else None
    svc = _make_service()
    return jsonify(
        [
            e.to_dict()
            for e in svc.list(
                ListEmployeesCommand(
                    area_id=area_id,
                    role=request.args.get("role"),
                    active=active,
                )
            )
        ]
    )


@employees_bp.get("/<int:eid>")
@schema(response=Employee)
def get_employee(eid: int):
    svc = _make_service()
    try:
        return jsonify(svc.get(eid).to_dict())
    except HRError as e:
        return _err(str(e), e.status)


@employees_bp.post("/<int:eid>/promote")
@schema(request=PromoteRequest, response=Employee)
def promote(eid: int):
    data = request.get_json(silent=True) or {}
    if "salary_increase_pct" not in data:
        return _err("missing field: salary_increase_pct", 400)
    svc = _make_service()
    try:
        emp = svc.promote(
            PromoteCommand(
                employee_id=eid, salary_increase_pct=data["salary_increase_pct"]
            )
        )
    except HRError as e:
        return _err(str(e), e.status)
    return jsonify(emp.to_dict())


@employees_bp.post("/<int:eid>/manager")
@schema(request=AssignManagerRequest, response=Employee)
def assign_manager(eid: int):
    data = request.get_json(silent=True) or {}
    if "manager_id" not in data:
        return _err("missing field: manager_id", 400)
    svc = _make_service()
    try:
        emp = svc.assign_manager(
            AssignManagerCommand(employee_id=eid, manager_id=data["manager_id"])
        )
    except HRError as e:
        return _err(str(e), e.status)
    return jsonify(emp.to_dict())


@employees_bp.get("/<int:eid>/team")
@schema(response=Employee, many=True)
def get_team(eid: int):
    svc = _make_service()
    try:
        return jsonify([e.to_dict() for e in svc.get_team(eid)])
    except HRError as e:
        return _err(str(e), e.status)


@employees_bp.patch("/<int:eid>/status")
@schema(response=Employee)
def toggle_status(eid: int):
    svc = _make_service()
    try:
        return jsonify(
            svc.toggle_active(ToggleStatusCommand(employee_id=eid)).to_dict()
        )
    except HRError as e:
        return _err(str(e), e.status)


@employees_bp.patch("/<int:eid>/area")
@schema(request=AssignAreaRequest, response=Employee)
def assign_area(eid: int):
    data = request.get_json(silent=True) or {}
    if "area_id" not in data:
        return _err("missing field: area_id", 400)
    svc = _make_service()
    try:
        return jsonify(
            svc.assign_area(
                AssignAreaCommand(employee_id=eid, area_id=data["area_id"])
            ).to_dict()
        )
    except HRError as e:
        return _err(str(e), e.status)
