#!/usr/bin/env python3
"""
Generate an OpenAPI 3.0 skeleton from any Flask app factory.

Usage:
  python scripts/gen_openapi.py <src_path> <app_module> [options]

Examples:
  python scripts/gen_openapi.py modules/products/src products.app
  python scripts/gen_openapi.py modules/hr/src hr.app --out hr-openapi.json --title "HR API"
"""
import argparse
import dataclasses
import importlib
import json
import re
import sys
from pathlib import Path

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


# ── Schema converters ──────────────────────────────────────────────────────────

def _py_to_schema(tp) -> dict:
    """Convert a Python type annotation to a JSON Schema dict."""
    import datetime
    from typing import Union, get_args, get_origin

    primitives = {
        str:              {"type": "string"},
        int:              {"type": "integer"},
        float:            {"type": "number"},
        bool:             {"type": "boolean"},
        datetime.date:    {"type": "string", "format": "date"},
        datetime.datetime:{"type": "string", "format": "date-time"},
    }
    if tp in primitives:
        return primitives[tp].copy()

    origin = get_origin(tp)
    args = get_args(tp)

    if origin is Union:
        non_none = [a for a in args if a is not type(None)]
        return _py_to_schema(non_none[0]) if non_none else {"type": "string"}

    if origin is list:
        return {"type": "array", "items": _py_to_schema(args[0]) if args else {"type": "string"}}

    try:
        import enum
        if isinstance(tp, type) and issubclass(tp, enum.Enum):
            return {"type": "string", "enum": [e.value for e in tp]}
    except Exception:
        pass

    return {"type": "string"}


def _dataclass_schema(cls) -> dict:
    """Dataclass → JSON Schema (required fields derived from defaults/Optional)."""
    import typing
    from typing import Union, get_args, get_origin

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
        is_optional = (
            get_origin(hint) is Union and type(None) in get_args(hint)
        )
        has_default = (
            f.default is not dataclasses.MISSING
            or f.default_factory is not dataclasses.MISSING  # type: ignore[misc]
        )
        properties[f.name] = _py_to_schema(hint)
        if not has_default and not is_optional:
            required.append(f.name)

    result: dict = {"type": "object", "properties": properties}
    if required:
        result["required"] = required
    return result


def _model_schema(model_cls) -> dict:
    """SQLAlchemy model → JSON Schema via column inspection."""
    from sqlalchemy import inspect as sa_inspect
    from sqlalchemy import (
        Boolean, Date, DateTime, Enum as SAEnum,
        Integer, Numeric, String, Text,
    )

    _SA = {
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
        s: dict = {"type": "string"}
        for sa_type, js in _SA.items():
            if isinstance(col.type, sa_type):
                s = js.copy()
                if isinstance(col.type, SAEnum) and col.type.enums:
                    s["enum"] = list(col.type.enums)
                break
        if col.nullable:
            s["nullable"] = True
        properties[col.key] = s

    return {"type": "object", "properties": properties}


def _resolve_schema(cls, defs: dict) -> dict:
    """Convert a class to a $ref entry in defs and return a $ref dict."""
    name = cls.__name__
    if name not in defs:
        if dataclasses.is_dataclass(cls):
            defs[name] = _dataclass_schema(cls)
        else:
            defs[name] = _model_schema(cls)
    return {"$ref": f"#/components/schemas/{name}"}


# ── Operation builder ──────────────────────────────────────────────────────────

def _operation(rule_endpoint: str, method: str, path_params: list[dict], func, defs: dict) -> dict:
    status = getattr(func, "__openapi_status__", 200)
    request_cls = getattr(func, "__openapi_request__", None)
    query_cls = getattr(func, "__openapi_query__", None)
    response_cls = getattr(func, "__openapi_response__", None)
    many = getattr(func, "__openapi_many__", False)

    op: dict = {
        "operationId": f"{method.lower()}_{rule_endpoint}",
        "responses": {},
    }

    # Path parameters
    parameters = list(path_params)

    # Query parameters from a filter dataclass
    if query_cls is not None and dataclasses.is_dataclass(query_cls):
        import typing
        from typing import Union, get_args, get_origin

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
                "schema": _py_to_schema(hint),
            })

    if parameters:
        op["parameters"] = parameters

    # Request body
    if request_cls is not None:
        op["requestBody"] = {
            "required": True,
            "content": {
                "application/json": {
                    "schema": _resolve_schema(request_cls, defs),
                }
            },
        }

    # Success response
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


# ── Top-level builder ──────────────────────────────────────────────────────────

def build_spec(app, title: str, version: str) -> dict:
    defs: dict = {}
    spec: dict = {
        "openapi": "3.0.3",
        "info": {"title": title, "version": version},
        "paths": {},
    }

    for rule in sorted(app.url_map.iter_rules(), key=lambda r: r.rule):
        if rule.rule.startswith("/static"):
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


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate an OpenAPI 3.0 skeleton from a Flask app factory."
    )
    parser.add_argument("src_path", help="Directory to add to sys.path (e.g. modules/products/src)")
    parser.add_argument("app_module", help="Dotted module path with create_app (e.g. products.app)")
    parser.add_argument("--out", default=None, help="Output file (default: <package>-openapi.json)")
    parser.add_argument("--title", default=None, help="API title (default: derived from module name)")
    parser.add_argument("--version", default="0.1.0", help="API version (default: 0.1.0)")
    args = parser.parse_args()

    src = Path(args.src_path).resolve()
    # Add src dir and modules/ so that `lib.openapi` is importable alongside app modules
    for p in [src, src.parent.parent]:
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))

    mod = importlib.import_module(args.app_module)
    app = mod.create_app(db_url="sqlite:///:memory:")

    package = args.app_module.split(".")[0]
    title = args.title or f"{package.replace('_', ' ').title()} API"
    out = Path(args.out or f"{package}-openapi.json")

    spec = build_spec(app, title=title, version=args.version)
    out.write_text(json.dumps(spec, indent=2))

    n_paths = len(spec["paths"])
    n_ops = sum(len(v) for v in spec["paths"].values())
    n_schemas = len(spec.get("components", {}).get("schemas", {}))
    print(f"✓ {out}  ({n_paths} paths, {n_ops} operations, {n_schemas} schemas)")


if __name__ == "__main__":
    main()
