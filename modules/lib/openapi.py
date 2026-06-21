"""Lightweight OpenAPI metadata decorator and schema converters.

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
"""
import dataclasses
import datetime
from typing import Any, Union, get_args, get_origin


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
    str:              {"type": "string"},
    int:              {"type": "integer"},
    float:            {"type": "number"},
    bool:             {"type": "boolean"},
    datetime.date:    {"type": "string", "format": "date"},
    datetime.datetime:{"type": "string", "format": "date-time"},
}


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
