"""Lightweight OpenAPI 3.0 decorator, schema converters, and route installer.

Usage in a blueprint:

    from lib.openapi import schema

    @bp.post("")
    @schema(request=CreateProductRequest, response=Product, status=201,
            summary="Create a product")
    def create():
        \"\"\"Creates a new product and publishes a product.created event.\"\"\"
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
"""

from __future__ import annotations

import datetime
import enum
import re
import typing
from typing import Any, Literal, Union, get_args, get_origin

from pydantic import BaseModel, ConfigDict

# ── Public decorator ───────────────────────────────────────────────────────────


def schema(
    *,
    request: Any = None,
    query: Any = None,
    response: Any = None,
    many: bool = False,
    status: int = 200,
    summary: str | None = None,
    description: str | None = None,
    deprecated: bool = False,
):
    """Attach OpenAPI metadata to a Flask route handler.

    Args:
        request:     Pydantic model for the JSON request body.
        query:       Pydantic model whose fields become query-string parameters.
        response:    Pydantic model or SQLAlchemy model returned by the endpoint.
        many:        True when the response is a list of *response*.
        status:      success HTTP status code.
        summary:     short one-line description shown in collapsed operation row.
        description: longer description; falls back to the view function's docstring.
        deprecated:  marks the operation as deprecated in the spec.
    """

    def decorator(func):
        func.__openapi_request__ = request
        func.__openapi_query__ = query
        func.__openapi_response__ = response
        func.__openapi_many__ = many
        func.__openapi_status__ = status
        func.__openapi_summary__ = summary
        func.__openapi_description__ = description
        func.__openapi_deprecated__ = deprecated
        return func

    return decorator


# ── Constants ──────────────────────────────────────────────────────────────────

_SKIP_METHODS: frozenset[str] = frozenset({"HEAD", "OPTIONS"})
_INTERNAL_ROUTES: frozenset[str] = frozenset({"/openapi.json", "/docs"})

_PY_TO_JSON: dict[type, dict] = {
    str: {"type": "string"},
    int: {"type": "integer"},
    float: {"type": "number"},
    bool: {"type": "boolean"},
    dict: {"type": "object"},
    datetime.date: {"type": "string", "format": "date"},
    datetime.datetime: {"type": "string", "format": "date-time"},
}

_FLASK_CONVERTER_MAP: dict[str, dict] = {
    "int": {"type": "integer"},
    "float": {"type": "number", "format": "float"},
    "uuid": {"type": "string", "format": "uuid"},
    "path": {"type": "string"},
    "string": {"type": "string"},
    "any": {"type": "string"},
}

# Shared error body registered once in components/schemas.
_ERROR_RESPONSE_SCHEMA: dict = {
    "type": "object",
    "properties": {"error": {"type": "string"}},
    "required": ["error"],
}
_ERROR_REF: dict = {"$ref": "#/components/schemas/ErrorResponse"}


# ── Endpoint metadata ──────────────────────────────────────────────────────────


class _EndpointMeta(BaseModel):
    """All @schema() attributes collected from a single view function."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    request_cls: Any
    query_cls: Any
    response_cls: Any
    many: bool
    status: int
    summary: str | None
    description: str | None
    deprecated: bool

    @classmethod
    def from_view(cls, func: Any) -> _EndpointMeta:
        explicit_desc = getattr(func, "__openapi_description__", None)
        return cls(
            request_cls=getattr(func, "__openapi_request__", None),
            query_cls=getattr(func, "__openapi_query__", None),
            response_cls=getattr(func, "__openapi_response__", None),
            many=getattr(func, "__openapi_many__", False),
            status=getattr(func, "__openapi_status__", 200),
            summary=getattr(func, "__openapi_summary__", None),
            description=explicit_desc
            if explicit_desc is not None
            else _extract_docstring(func),
            deprecated=getattr(func, "__openapi_deprecated__", False),
        )


def _extract_docstring(func: Any) -> str | None:
    """Return the first non-blank line of *func*'s docstring, or None."""
    doc = getattr(func, "__doc__", None)
    if not doc:
        return None
    lines = [line.strip() for line in doc.strip().splitlines()]
    return next((line for line in lines if line), None)


# ── Type → JSON Schema converters ─────────────────────────────────────────────


def _annotation_to_schema(tp: Any) -> dict:
    if tp in _PY_TO_JSON:
        return dict(_PY_TO_JSON[tp])

    origin = get_origin(tp)
    args = get_args(tp)

    # Literal["a", "b"] → enum of those values
    if origin is Literal:
        values = list(args)
        base = (
            dict(_PY_TO_JSON.get(type(values[0]), {"type": "string"}))
            if values
            else {"type": "string"}
        )
        return {**base, "enum": values}

    # Optional[X] = Union[X, None] → unwrap to X (nullability expressed via `required`)
    if origin is Union:
        non_none = [a for a in args if a is not type(None)]
        if non_none:
            return _annotation_to_schema(non_none[0])

    # list[X] / List[X]
    if origin is list:
        items = _annotation_to_schema(args[0]) if args else {"type": "string"}
        return {"type": "array", "items": items}

    # dict[K, V] / Dict[K, V]
    if origin is dict:
        if len(args) > 1:
            return {
                "type": "object",
                "additionalProperties": _annotation_to_schema(args[1]),
            }
        return {"type": "object"}

    # Enum subclass
    if isinstance(tp, type) and issubclass(tp, enum.Enum):
        return {"type": "string", "enum": [e.value for e in tp]}

    return {"type": "string"}


def _is_pydantic(cls: Any) -> bool:
    return isinstance(cls, type) and issubclass(cls, BaseModel)


def pydantic_to_schema(cls: Any) -> dict:
    """Convert a Pydantic v2 BaseModel to a JSON Schema object."""
    if not _is_pydantic(cls):
        return {"type": "object"}

    try:
        hints = typing.get_type_hints(cls)
    except Exception:
        hints = dict.fromkeys(cls.model_fields, Any)

    properties: dict[str, dict] = {}
    required: list[str] = []

    for name, field_info in cls.model_fields.items():
        hint = hints.get(name, Any)
        properties[name] = _annotation_to_schema(hint)
        if field_info.is_required():
            required.append(name)

    result: dict = {"type": "object", "properties": properties}
    if required:
        result["required"] = required
    return result


def model_to_schema(model_cls: Any) -> dict:
    """Convert a SQLAlchemy declarative model to a JSON Schema object."""
    from sqlalchemy import (
        Boolean,
        Date,
        DateTime,
        Enum as SAEnum,
        Integer,
        Numeric,
        String,
        Text,
        inspect as sa_inspect,
    )

    _sa_map: dict = {
        Integer: {"type": "integer"},
        String: {"type": "string"},
        Text: {"type": "string"},
        Numeric: {"type": "number"},
        Boolean: {"type": "boolean"},
        Date: {"type": "string", "format": "date"},
        DateTime: {"type": "string", "format": "date-time"},
        SAEnum: {"type": "string"},
    }

    try:
        mapper = sa_inspect(model_cls)
    except Exception:
        return {"type": "object"}

    properties: dict[str, dict] = {}
    for col in mapper.columns:
        col_schema: dict = {"type": "string"}
        for sa_type, js in _sa_map.items():
            if isinstance(col.type, sa_type):
                col_schema = dict(js)
                if isinstance(col.type, SAEnum) and col.type.enums:
                    col_schema["enum"] = list(col.type.enums)
                break
        if col.nullable:
            col_schema["nullable"] = True
        properties[col.key] = col_schema

    return {"type": "object", "properties": properties}


# ── URL / path helpers ─────────────────────────────────────────────────────────


def _flask_rule_to_openapi(rule: str) -> tuple[str, list[dict]]:
    """Convert ``/items/<int:id>`` → ``("/items/{id}", [path_param_dict])``."""
    params: list[dict] = []

    def _replace(m: re.Match) -> str:
        raw = m.group(1)
        converter, name = raw.split(":", 1) if ":" in raw else ("string", raw)
        params.append(
            {
                "name": name,
                "in": "path",
                "required": True,
                "schema": _FLASK_CONVERTER_MAP.get(converter, {"type": "string"}),
            }
        )
        return f"{{{name}}}"

    return re.sub(r"<([^>]+)>", _replace, rule), params


def _endpoint_tag(endpoint: str) -> str:
    """``'products.create_product'`` → ``'products'``, ``'index'`` → ``'general'``."""
    return endpoint.split(".")[0] if "." in endpoint else "general"


# ── Schema registry ────────────────────────────────────────────────────────────


def _register_schema(cls: Any, defs: dict) -> dict:
    """Ensure *cls* has an entry in *defs* and return a ``$ref`` to it."""
    name = cls.__name__
    if name not in defs:
        defs[name] = (
            pydantic_to_schema(cls) if _is_pydantic(cls) else model_to_schema(cls)
        )
    return {"$ref": f"#/components/schemas/{name}"}


# ── Per-operation builders ─────────────────────────────────────────────────────


def _build_query_params(query_cls: Any) -> list[dict]:
    if query_cls is None or not _is_pydantic(query_cls):
        return []

    try:
        hints = typing.get_type_hints(query_cls)
    except Exception:
        hints = {}

    params: list[dict] = []
    for name, field_info in query_cls.model_fields.items():
        hint = hints.get(name, str)
        is_optional = get_origin(hint) is Union and type(None) in get_args(hint)
        params.append(
            {
                "name": name,
                "in": "query",
                "required": not is_optional and field_info.is_required(),
                "schema": _annotation_to_schema(hint),
            }
        )
    return params


def _build_request_body(request_cls: Any, defs: dict) -> dict | None:
    if request_cls is None:
        return None
    return {
        "required": True,
        "content": {
            "application/json": {"schema": _register_schema(request_cls, defs)},
        },
    }


def _build_response(
    response_cls: Any, many: bool, status: int, defs: dict
) -> tuple[str, dict]:
    """Return ``(status_code_str, response_object)`` for the success case."""
    if response_cls is None:
        return str(status), {"description": "No content" if status == 204 else "OK"}

    ref = _register_schema(response_cls, defs)
    body_schema = {"type": "array", "items": ref} if many else ref
    return str(status), {
        "description": "OK",
        "content": {"application/json": {"schema": body_schema}},
    }


def _build_operation(
    endpoint: str,
    method: str,
    path_params: list[dict],
    meta: _EndpointMeta,
    defs: dict,
) -> dict:
    op: dict = {
        "operationId": f"{method.lower()}_{endpoint}",
        "tags": [_endpoint_tag(endpoint)],
        "responses": {},
    }

    if meta.summary:
        op["summary"] = meta.summary
    if meta.description:
        op["description"] = meta.description
    if meta.deprecated:
        op["deprecated"] = True

    parameters = path_params + _build_query_params(meta.query_cls)
    if parameters:
        op["parameters"] = parameters

    request_body = _build_request_body(meta.request_cls, defs)
    if request_body is not None:
        op["requestBody"] = request_body

    status_key, response_obj = _build_response(
        meta.response_cls, meta.many, meta.status, defs
    )
    op["responses"][status_key] = response_obj
    op["responses"]["400"] = {
        "description": "Bad request",
        "content": {"application/json": {"schema": _ERROR_REF}},
    }
    op["responses"]["404"] = {
        "description": "Not found",
        "content": {"application/json": {"schema": _ERROR_REF}},
    }

    return op


# ── Spec builder ───────────────────────────────────────────────────────────────


def build_spec(
    app: Any,
    title: str,
    version: str,
    security_schemes: dict | None = None,
) -> dict:
    """Build a full OpenAPI 3.0.3 spec dict from a Flask app's URL map.

    Args:
        app:              Flask application instance.
        title:            API title.
        version:          API version string.
        security_schemes: Optional OpenAPI security scheme objects; when given,
                          every operation inherits a global security requirement.
    """
    # Seed with the shared error schema so all 400/404 refs resolve.
    defs: dict = {"ErrorResponse": _ERROR_RESPONSE_SCHEMA}
    seen_tags: list[str] = []
    paths: dict = {}

    for rule in sorted(app.url_map.iter_rules(), key=lambda r: r.rule):
        if rule.rule.startswith("/static") or rule.rule in _INTERNAL_ROUTES:
            continue
        methods = sorted(rule.methods - _SKIP_METHODS)
        if not methods:
            continue

        path, path_params = _flask_rule_to_openapi(rule.rule)
        meta = _EndpointMeta.from_view(app.view_functions.get(rule.endpoint))
        tag = _endpoint_tag(rule.endpoint)

        if tag not in seen_tags:
            seen_tags.append(tag)

        path_item = paths.setdefault(path, {})
        for method in methods:
            path_item[method.lower()] = _build_operation(
                rule.endpoint, method, path_params, meta, defs
            )

    spec: dict = {
        "openapi": "3.0.3",
        "info": {"title": title, "version": version},
        "paths": paths,
    }

    if seen_tags:
        spec["tags"] = [
            {"name": t, "description": f"{t.replace('_', ' ').title()} endpoints"}
            for t in seen_tags
        ]

    components: dict = {}
    if defs:
        components["schemas"] = defs
    if security_schemes:
        components["securitySchemes"] = security_schemes
        spec["security"] = [{name: []} for name in security_schemes]
    if components:
        spec["components"] = components

    return spec


# ── Route installer ────────────────────────────────────────────────────────────


def install_openapi_route(
    app: Any,
    title: str | None = None,
    version: str = "0.1.0",
    jwt: bool = True,
) -> None:
    """Register GET /openapi.json and GET /docs (Swagger UI) on the Flask app.

    The spec is built lazily on first request so all blueprints registered
    after this call are still included.

    Args:
        app:     Flask application instance.
        title:   API title; defaults to the app name.
        version: API version string.
        jwt:     Add a BearerAuth JWT security scheme and enable the
                 Authorize button in Swagger UI.
    """
    from pathlib import Path
    from string import Template

    from flask import jsonify, make_response

    resolved_title = title or f"{app.name.replace('_', ' ').title()} API"
    security_schemes: dict | None = (
        {
            "BearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
                "description": "Paste your JWT token (without the 'Bearer ' prefix).",
            }
        }
        if jwt
        else None
    )

    spec_cache: dict = {}
    ui_template = Template(
        (Path(__file__).parent / "swagger_ui.html").read_text(encoding="utf-8")
    )

    @app.get("/openapi.json")
    def _openapi_json():
        if not spec_cache:
            spec_cache.update(
                build_spec(
                    app,
                    title=resolved_title,
                    version=version,
                    security_schemes=security_schemes,
                )
            )
        return jsonify(spec_cache)

    @app.get("/docs")
    def _swagger_ui():
        html = ui_template.substitute(
            title=resolved_title,
            persist_authorization="persistAuthorization: true," if jwt else "",
        )
        return make_response(html, 200, {"Content-Type": "text/html; charset=utf-8"})
