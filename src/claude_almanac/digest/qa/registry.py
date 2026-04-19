"""Tool registry for digest Q&A (extensible by downstream plans + forks).

Tools register via `@REGISTRY.tool(name, description)`. The decorator inspects
signature annotations to generate an Anthropic-compatible input_schema; the
same schema is re-used when wrapping tools as claude-agent-sdk `@tool`s in
deep mode. `auto_discover(pkg)` imports every module under `pkg` so tools
self-register by side effect.

Extension point (Plan 2): additional packages (e.g.,
`claude_almanac.codeindex.digest_tools`) call
`registry.auto_discover('claude_almanac.codeindex.digest_tools')` from deep
mode's init, or simply `from ...registry import tool` and decorate their
callables at import time. Do NOT add cross-subsystem tools in this plan;
they belong to whichever subsystem owns the underlying data.
"""
from __future__ import annotations

import importlib
import inspect
import pkgutil
import types
import typing
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Union

_PY_TO_JSON = {
    str: "string", int: "integer", float: "number",
    bool: "boolean", list: "array", dict: "object",
}


def _python_type_to_json(anno: Any) -> dict[str, Any]:
    origin = typing.get_origin(anno)
    if origin is Union or origin is types.UnionType:
        args = [a for a in typing.get_args(anno) if a is not type(None)]
        if len(args) == 1:
            return _python_type_to_json(args[0])
    if origin is list:
        item = typing.get_args(anno)[0] if typing.get_args(anno) else str
        return {"type": "array", "items": _python_type_to_json(item)}
    return {"type": _PY_TO_JSON.get(anno, "string")}


@dataclass
class ToolEntry:
    name: str
    description: str
    fn: Callable[..., Any]
    schema: dict[str, Any]


class Registry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolEntry] = {}

    def tool(self, name: str, description: str) -> Callable:
        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            if name in self._tools:
                raise ValueError(f"tool '{name}' already registered")
            self._tools[name] = ToolEntry(
                name=name,
                description=description,
                fn=fn,
                schema=self._build_schema(name, description, fn),
            )
            return fn
        return decorator

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __getitem__(self, name: str) -> ToolEntry:
        return self._tools[name]

    def all(self) -> Iterable[ToolEntry]:
        return list(self._tools.values())

    def call(self, name: str, **kwargs: Any) -> Any:
        return self._tools[name].fn(**kwargs)

    @staticmethod
    def _build_schema(
        name: str, description: str, fn: Callable[..., Any],
    ) -> dict[str, Any]:
        sig = inspect.signature(fn)
        try:
            hints = typing.get_type_hints(fn)
        except Exception:
            hints = {}
        props: dict[str, Any] = {}
        required: list[str] = []
        for param in sig.parameters.values():
            if param.name == "self":
                continue
            anno = hints.get(param.name, param.annotation)
            props[param.name] = _python_type_to_json(anno)
            if param.default is inspect.Parameter.empty:
                required.append(param.name)
        return {
            "name": name,
            "description": description,
            "input_schema": {
                "type": "object",
                "properties": props,
                "required": required,
            },
        }


REGISTRY = Registry()


def tool(name: str, description: str) -> Callable:
    return REGISTRY.tool(name, description)


def auto_discover(
    package_name: str = "claude_almanac.digest.qa.tools",
    registry: Registry | None = None,
) -> None:
    global REGISTRY
    if registry is not None:
        saved = REGISTRY
        REGISTRY = registry
        try:
            pkg = importlib.import_module(package_name)
            for _finder, modname, _ispkg in pkgutil.iter_modules(pkg.__path__):
                importlib.import_module(f"{package_name}.{modname}")
        finally:
            REGISTRY = saved
        return
    pkg = importlib.import_module(package_name)
    for _finder, modname, _ispkg in pkgutil.iter_modules(pkg.__path__):
        importlib.import_module(f"{package_name}.{modname}")
