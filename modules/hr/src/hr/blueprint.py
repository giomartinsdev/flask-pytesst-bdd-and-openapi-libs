import os
from flask import Blueprint, current_app, jsonify, request
import boto3
from sqlalchemy.orm import Session

from lib.openapi import schema

from .models import Employee
from .schemas import AssignManagerRequest, EmployeeFilters, HireRequest, PromoteRequest
from .service import HRError, HRService

hr_bp = Blueprint("hr", __name__, url_prefix="/employees")


def _make_service() -> HRService:
    session: Session = current_app.config["SESSION_FACTORY"]()
    ep = os.environ.get("AWS_ENDPOINT_URL")
    return HRService(
        session=session,
        sqs_client=boto3.client("sqs", endpoint_url=ep, region_name="us-east-1"),
        sns_client=boto3.client("sns", endpoint_url=ep, region_name="us-east-1"),
        sqs_queue_url=os.environ.get("HR_QUEUE_URL", ""),
        sns_topic_arn=os.environ.get("HR_TOPIC_ARN", ""),
    )


def _err(msg: str, status: int):
    return jsonify({"error": msg}), status


@hr_bp.post("")
@schema(request=HireRequest, response=Employee, status=201)
def hire():
    data = request.get_json(silent=True) or {}
    missing = [f for f in ("name", "email", "department", "role", "salary") if f not in data]
    if missing:
        return _err(f"missing fields: {', '.join(missing)}", 400)
    from datetime import date
    def _parse_date(v):
        return date.fromisoformat(v) if v else None
    svc = _make_service()
    try:
        emp = svc.hire(HireRequest(
            name=data["name"], email=data["email"], department=data["department"],
            role=data["role"], salary=data["salary"],
            hire_date=_parse_date(data.get("hire_date")),
            role_since=_parse_date(data.get("role_since")),
        ))
    except HRError as e:
        return _err(str(e), e.status)
    return jsonify(emp.to_dict()), 201


@hr_bp.get("")
@schema(query=EmployeeFilters, response=Employee, many=True)
def list_employees():
    active_param = request.args.get("active")
    active = None if active_param is None else active_param.lower() == "true"
    svc = _make_service()
    employees = svc.list_employees(EmployeeFilters(
        department=request.args.get("department"),
        role=request.args.get("role"),
        active=active,
    ))
    return jsonify([e.to_dict() for e in employees])


@hr_bp.get("/<int:eid>")
@schema(response=Employee)
def get_employee(eid: int):
    svc = _make_service()
    try:
        return jsonify(svc.get(eid).to_dict())
    except HRError as e:
        return _err(str(e), e.status)


@hr_bp.post("/<int:eid>/promote")
@schema(request=PromoteRequest, response=Employee)
def promote(eid: int):
    data = request.get_json(silent=True) or {}
    if "salary_increase_pct" not in data:
        return _err("missing field: salary_increase_pct", 400)
    svc = _make_service()
    try:
        emp = svc.promote(eid, PromoteRequest(salary_increase_pct=data["salary_increase_pct"]))
    except HRError as e:
        return _err(str(e), e.status)
    return jsonify(emp.to_dict())


@hr_bp.post("/<int:eid>/manager")
@schema(request=AssignManagerRequest, response=Employee)
def assign_manager(eid: int):
    data = request.get_json(silent=True) or {}
    if "manager_id" not in data:
        return _err("missing field: manager_id", 400)
    svc = _make_service()
    try:
        emp = svc.assign_manager(eid, AssignManagerRequest(manager_id=data["manager_id"]))
    except HRError as e:
        return _err(str(e), e.status)
    return jsonify(emp.to_dict())


@hr_bp.get("/<int:eid>/team")
@schema(response=Employee, many=True)
def get_team(eid: int):
    svc = _make_service()
    try:
        return jsonify([e.to_dict() for e in svc.get_team(eid)])
    except HRError as e:
        return _err(str(e), e.status)


@hr_bp.patch("/<int:eid>/status")
@schema(response=Employee)
def toggle_status(eid: int):
    svc = _make_service()
    try:
        return jsonify(svc.toggle_active(eid).to_dict())
    except HRError as e:
        return _err(str(e), e.status)
