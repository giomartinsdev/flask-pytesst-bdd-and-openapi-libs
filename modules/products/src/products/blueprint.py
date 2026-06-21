import os
from flask import Blueprint, current_app, jsonify, request
import boto3
from sqlalchemy.orm import Session

from .schemas import CreateProductRequest, ProductFilters, UpdateProductRequest
from .service import ProductError, ProductService

products_bp = Blueprint("products", __name__, url_prefix="/products")


def _make_service() -> ProductService:
    session: Session = current_app.config["SESSION_FACTORY"]()
    ep = os.environ.get("AWS_ENDPOINT_URL")
    return ProductService(
        session=session,
        sqs_client=boto3.client("sqs", endpoint_url=ep, region_name="us-east-1"),
        sns_client=boto3.client("sns", endpoint_url=ep, region_name="us-east-1"),
        s3_client=boto3.client("s3", endpoint_url=ep, region_name="us-east-1"),
        sqs_queue_url=os.environ.get("SQS_QUEUE_URL", ""),
        sns_topic_arn=os.environ.get("SNS_TOPIC_ARN", ""),
        s3_bucket=os.environ.get("S3_BUCKET", ""),
    )


def _error(message: str, status: int):
    return jsonify({"error": message}), status


@products_bp.post("")
def create_product():
    data = request.get_json(silent=True) or {}
    missing = [f for f in ("name", "category", "price") if f not in data]
    if missing:
        return _error(f"missing fields: {', '.join(missing)}", 400)
    svc = _make_service()
    try:
        product = svc.create(CreateProductRequest(
            name=data["name"], category=data["category"], price=data["price"],
            stock=data.get("stock", 0), active=data.get("active", True),
        ))
    except ProductError as e:
        return _error(str(e), e.status)
    return jsonify(product.to_dict()), 201


@products_bp.get("")
def list_products():
    active_param = request.args.get("active")
    active = None if active_param is None else active_param.lower() == "true"
    svc = _make_service()
    products = svc.list_all(ProductFilters(category=request.args.get("category"), active=active))
    return jsonify([p.to_dict() for p in products])


@products_bp.get("/<int:product_id>")
def get_product(product_id: int):
    svc = _make_service()
    try:
        return jsonify(svc.get(product_id).to_dict())
    except ProductError as e:
        return _error(str(e), e.status)


@products_bp.put("/<int:product_id>")
def update_product(product_id: int):
    data = request.get_json(silent=True) or {}
    svc = _make_service()
    try:
        product = svc.update(product_id, UpdateProductRequest(
            name=data.get("name"), category=data.get("category"), price=data.get("price"),
        ))
    except ProductError as e:
        return _error(str(e), e.status)
    return jsonify(product.to_dict())


@products_bp.patch("/<int:product_id>/stock")
def update_stock(product_id: int):
    data = request.get_json(silent=True) or {}
    if "stock" not in data:
        return _error("missing field: stock", 400)
    svc = _make_service()
    try:
        return jsonify(svc.update_stock(product_id, data["stock"]).to_dict())
    except ProductError as e:
        return _error(str(e), e.status)


@products_bp.patch("/<int:product_id>/status")
def toggle_status(product_id: int):
    svc = _make_service()
    try:
        return jsonify(svc.toggle_status(product_id).to_dict())
    except ProductError as e:
        return _error(str(e), e.status)


@products_bp.delete("/<int:product_id>")
def delete_product(product_id: int):
    svc = _make_service()
    try:
        svc.delete(product_id)
    except ProductError as e:
        return _error(str(e), e.status)
    return "", 204
