import os
from flask import Blueprint, current_app, jsonify, request
import boto3
from sqlalchemy.orm import Session

from lib.openapi import schema

from hr.domain.area.model import Area
from hr.domain.employee.model import Employee
from hr.domain.area.repository import AreaRepository
from hr.domain.employee.repository import EmployeeRepository
from hr.domain.area.commands import CreateAreaCommand, UpdateAreaCommand, AssignHeadCommand, DeleteAreaCommand
from hr.application.area_service import AreaApplicationService
from hr.application.employee_service import HRError
from hr.application.event_bus import EventBus
from hr.api.areas.schemas import CreateAreaRequest, UpdateAreaRequest, AssignHeadRequest

areas_bp = Blueprint("areas", __name__, url_prefix="/areas")


def _make_service() -> AreaApplicationService:
    session: Session = current_app.config["SESSION_FACTORY"]()
    ep = os.environ.get("AWS_ENDPOINT_URL")
    bus = EventBus(
        sqs_client=boto3.client("sqs", endpoint_url=ep, region_name="us-east-1"),
        sns_client=boto3.client("sns", endpoint_url=ep, region_name="us-east-1"),
        queue_url=os.environ.get("HR_QUEUE_URL", ""),
        topic_arn=os.environ.get("HR_TOPIC_ARN", ""),
    )
    return AreaApplicationService(
        area_repo=AreaRepository(session),
        employee_repo=EmployeeRepository(session),
        event_bus=bus,
    )


def _err(msg: str, status: int):
    return jsonify({"error": msg}), status


@areas_bp.post("")
@schema(request=CreateAreaRequest, response=Area, status=201)
def create_area():
    data = request.get_json(silent=True) or {}
    if "name" not in data:
        return _err("missing field: name", 400)
    svc = _make_service()
    try:
        area = svc.create(CreateAreaCommand(name=data["name"], description=data.get("description")))
    except HRError as e:
        return _err(str(e), e.status)
    return jsonify(area.to_dict()), 201


@areas_bp.get("")
@schema(response=Area, many=True)
def list_areas():
    svc = _make_service()
    return jsonify([a.to_dict() for a in svc.list()])


@areas_bp.get("/<int:area_id>")
@schema(response=Area)
def get_area(area_id: int):
    svc = _make_service()
    try:
        return jsonify(svc.get(area_id).to_dict())
    except HRError as e:
        return _err(str(e), e.status)


@areas_bp.put("/<int:area_id>")
@schema(request=UpdateAreaRequest, response=Area)
def update_area(area_id: int):
    data = request.get_json(silent=True) or {}
    svc = _make_service()
    try:
        area = svc.update(UpdateAreaCommand(
            area_id=area_id, name=data.get("name"), description=data.get("description"),
        ))
    except HRError as e:
        return _err(str(e), e.status)
    return jsonify(area.to_dict())


@areas_bp.patch("/<int:area_id>/head")
@schema(request=AssignHeadRequest, response=Area)
def assign_head(area_id: int):
    data = request.get_json(silent=True) or {}
    if "head_employee_id" not in data:
        return _err("missing field: head_employee_id", 400)
    svc = _make_service()
    try:
        area = svc.assign_head(AssignHeadCommand(
            area_id=area_id, head_employee_id=data["head_employee_id"],
        ))
    except HRError as e:
        return _err(str(e), e.status)
    return jsonify(area.to_dict())


@areas_bp.get("/<int:area_id>/employees")
@schema(response=Employee, many=True)
def list_area_employees(area_id: int):
    svc = _make_service()
    try:
        return jsonify([e.to_dict() for e in svc.get_members(area_id)])
    except HRError as e:
        return _err(str(e), e.status)


@areas_bp.delete("/<int:area_id>")
@schema(status=204)
def delete_area(area_id: int):
    svc = _make_service()
    try:
        svc.delete(DeleteAreaCommand(area_id=area_id))
    except HRError as e:
        return _err(str(e), e.status)
    return "", 204
