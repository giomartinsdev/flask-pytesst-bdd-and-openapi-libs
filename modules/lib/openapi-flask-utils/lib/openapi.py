"""Lightweight OpenAPI metadata decorator, schema converters, and route installer.

Usage in a blueprint:

    from lib.openapi import schema
    from .schemas import CreateProductRequest
    from .models import Product

    @bp.post("")
    @schema(request=CreateProductRequest, response=Product, status=201)
    def create():
        ...

    @bp.get("")
    @schema(query=ProductFilters, response=Product, many=True)
    def list_all():
        ...

Usage in create_app():

    from lib.openapi import install_openapi_route

    def create_app(...) -> Flask:
        app = Flask(__name__)
        ...
        install_openapi_route(app, title="My API", version="0.1.0")
        return app

    # Clients can then GET /openapi.json
"""
import dataclasses
import datetime
import json
import re
from typing import Any, Union, get_args, get_origin


# ── Route decorator ────────────────────────────────────────────────────────────

def schema(
    *,
    request=None,
    query=None,
    response=None,
    many: bool = False,
    status: int = 200,
):
    """Attach OpenAPI schema metadata to a Flask route handler.

    Args:
        request:  dataclass used as the JSON request body
        query:    dataclass whose fields become query-string parameters
        response: dataclass or SQLAlchemy model returned by the endpoint
        many:     True when the response is a list of `response`
        status:   success HTTP status code
    """
    def decorator(func):
        func.__openapi_request__ = request
        func.__openapi_query__ = query
        func.__openapi_response__ = response
        func.__openapi_many__ = many
        func.__openapi_status__ = status
        return func
    return decorator


# ── Type converters ────────────────────────────────────────────────────────────

_PY_PRIMITIVES: dict = {
    str:               {"type": "string"},
    int:               {"type": "integer"},
    float:             {"type": "number"},
    bool:              {"type": "boolean"},
    datetime.date:     {"type": "string", "format": "date"},
    datetime.datetime: {"type": "string", "format": "date-time"},
}

# Flask converter names → OpenAPI types
_FLASK_TYPE = {
    "int":    {"type": "integer"},
    "float":  {"type": "number", "format": "float"},
    "uuid":   {"type": "string", "format": "uuid"},
    "path":   {"type": "string"},
    "string": {"type": "string"},
    "any":    {"type": "string"},
}

_SKIP_METHODS = {"HEAD", "OPTIONS"}


def _annotation_to_schema(tp: Any) -> dict:
    if tp in _PY_PRIMITIVES:
        return _PY_PRIMITIVES[tp].copy()

    origin = get_origin(tp)
    args = get_args(tp)

    # Optional[X]  →  unwrap to X (nullability handled via `required`)
    if origin is Union:
        non_none = [a for a in args if a is not type(None)]
        if non_none:
            return _annotation_to_schema(non_none[0])

    # List[X]
    if origin is list:
        items = _annotation_to_schema(args[0]) if args else {"type": "string"}
        return {"type": "array", "items": items}

    # Enum subclass
    try:
        import enum
        if isinstance(tp, type) and issubclass(tp, enum.Enum):
            return {"type": "string", "enum": [e.value for e in tp]}
    except Exception:
        pass

    return {"type": "string"}


def dataclass_to_schema(cls) -> dict:
    """Convert a Python dataclass to a JSON Schema object."""
    import typing

    if not dataclasses.is_dataclass(cls):
        return {"type": "object"}

    try:
        hints = typing.get_type_hints(cls)
    except Exception:
        hints = {f.name: str for f in dataclasses.fields(cls)}

    properties: dict = {}
    required: list[str] = []

    for f in dataclasses.fields(cls):
        hint = hints.get(f.name, str)

        # Optional[X] = Union[X, None] → field is not required
        origin = get_origin(hint)
        args = get_args(hint)
        is_optional = origin is Union and type(None) in args

        properties[f.name] = _annotation_to_schema(hint)

        has_default = (
            f.default is not dataclasses.MISSING
            or f.default_factory is not dataclasses.MISSING  # type: ignore[misc]
        )
        if not has_default and not is_optional:
            required.append(f.name)

    result: dict = {"type": "object", "properties": properties}
    if required:
        result["required"] = required
    return result


def model_to_schema(model_cls) -> dict:
    """Convert a SQLAlchemy model to a JSON Schema object via column inspection."""
    from sqlalchemy import inspect as sa_inspect
    from sqlalchemy import (
        Boolean, Date, DateTime, Enum as SAEnum,
        Integer, Numeric, String, Text,
    )

    _SA_MAP = {
        Integer:  {"type": "integer"},
        String:   {"type": "string"},
        Text:     {"type": "string"},
        Numeric:  {"type": "number"},
        Boolean:  {"type": "boolean"},
        Date:     {"type": "string", "format": "date"},
        DateTime: {"type": "string", "format": "date-time"},
        SAEnum:   {"type": "string"},
    }

    try:
        mapper = sa_inspect(model_cls)
    except Exception:
        return {"type": "object"}

    properties: dict = {}
    for col in mapper.columns:
        col_schema: dict = {"type": "string"}
        for sa_type, js in _SA_MAP.items():
            if isinstance(col.type, sa_type):
                col_schema = js.copy()
                if isinstance(col.type, SAEnum) and col.type.enums:
                    col_schema["enum"] = list(col.type.enums)
                break
        if col.nullable:
            col_schema["nullable"] = True
        properties[col.key] = col_schema

    return {"type": "object", "properties": properties}


# ── Internal helpers ───────────────────────────────────────────────────────────

def _rule_to_openapi(rule: str) -> tuple[str, list[dict]]:
    params: list[dict] = []

    def _replace(m: re.Match) -> str:
        raw = m.group(1)
        converter, name = raw.split(":", 1) if ":" in raw else ("string", raw)
        params.append({
            "name": name,
            "in": "path",
            "required": True,
            "schema": _FLASK_TYPE.get(converter, {"type": "string"}),
        })
        return f"{{{name}}}"

    path = re.sub(r"<([^>]+)>", _replace, rule)
    return path, params


def _resolve_schema(cls, defs: dict) -> dict:
    """Register a class schema in defs and return a $ref dict."""
    name = cls.__name__
    if name not in defs:
        if dataclasses.is_dataclass(cls):
            defs[name] = dataclass_to_schema(cls)
        else:
            defs[name] = model_to_schema(cls)
    return {"$ref": f"#/components/schemas/{name}"}


def _operation(rule_endpoint: str, method: str, path_params: list[dict], func, defs: dict) -> dict:
    import typing
    from typing import Union, get_args, get_origin

    status = getattr(func, "__openapi_status__", 200)
    request_cls = getattr(func, "__openapi_request__", None)
    query_cls = getattr(func, "__openapi_query__", None)
    response_cls = getattr(func, "__openapi_response__", None)
    many = getattr(func, "__openapi_many__", False)

    op: dict = {
        "operationId": f"{method.lower()}_{rule_endpoint}",
        "responses": {},
    }

    parameters = list(path_params)

    if query_cls is not None and dataclasses.is_dataclass(query_cls):
        try:
            hints = typing.get_type_hints(query_cls)
        except Exception:
            hints = {f.name: str for f in dataclasses.fields(query_cls)}

        for f in dataclasses.fields(query_cls):
            hint = hints.get(f.name, str)
            is_optional = (
                get_origin(hint) is Union and type(None) in get_args(hint)
            )
            parameters.append({
                "name": f.name,
                "in": "query",
                "required": not is_optional and f.default is dataclasses.MISSING,
                "schema": _annotation_to_schema(hint),
            })

    if parameters:
        op["parameters"] = parameters

    if request_cls is not None:
        op["requestBody"] = {
            "required": True,
            "content": {
                "application/json": {
                    "schema": _resolve_schema(request_cls, defs),
                }
            },
        }

    if response_cls is not None:
        ref = _resolve_schema(response_cls, defs)
        body_schema = {"type": "array", "items": ref} if many else ref
        op["responses"][str(status)] = {
            "description": "OK",
            "content": {"application/json": {"schema": body_schema}},
        }
    else:
        op["responses"][str(status)] = {"description": "No content" if status == 204 else "OK"}

    op["responses"]["400"] = {"description": "Bad request"}
    op["responses"]["404"] = {"description": "Not found"}

    return op


# ── Spec builder ───────────────────────────────────────────────────────────────

def build_spec(app, title: str, version: str) -> dict:
    """Build a full OpenAPI 3.0.3 spec dict from a Flask app's URL map.

    Introspects every route decorated with @schema() and produces a complete
    OpenAPI document including paths, operations, and component schemas.
    """
    defs: dict = {}
    spec: dict = {
        "openapi": "3.0.3",
        "info": {"title": title, "version": version},
        "paths": {},
    }

    for rule in sorted(app.url_map.iter_rules(), key=lambda r: r.rule):
        if rule.rule.startswith("/static") or rule.rule == "/openapi.json":
            continue
        methods = sorted(rule.methods - _SKIP_METHODS)
        if not methods:
            continue

        path, path_params = _rule_to_openapi(rule.rule)
        spec["paths"].setdefault(path, {})
        func = app.view_functions.get(rule.endpoint)

        for method in methods:
            spec["paths"][path][method.lower()] = _operation(
                rule.endpoint, method, path_params, func, defs
            )

    if defs:
        spec["components"] = {"schemas": defs}

    return spec


# ── Route installer ────────────────────────────────────────────────────────────

def install_openapi_route(app, title: str = None, version: str = "0.1.0") -> None:
    """Register a GET /openapi.json route on the Flask app.

    The spec is built lazily on the first request so that all blueprints
    registered after this call are still included.

    Args:
        app:     A Flask application instance.
        title:   API title for the OpenAPI info object. Defaults to the app name.
        version: API version string (default "0.1.0").
    """
    from flask import jsonify

    _resolved_title = title or f"{app.name.replace('_', ' ').title()} API"
    _spec_cache: dict = {}

    @app.get("/openapi.json")
    def _openapi_json():
        if not _spec_cache:
            _spec_cache.update(build_spec(app, title=_resolved_title, version=version))
        return jsonify(_spec_cache)
