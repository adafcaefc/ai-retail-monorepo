from __future__ import annotations

import json
import re
from contextlib import AsyncExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, ForwardRef, Literal, Optional

from pydantic import AfterValidator, BaseModel, Field, create_model
from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

@dataclass
class ChivonAgent:
    name: str
    agent: Agent
    input_model: type[BaseModel]
    output_model: type[BaseModel]

_TEMPLATE_PATTERN = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)\s*\}\}")

def _render_template(template: str, ctx: dict[str, Any]) -> str:
    def replace(match: re.Match[str]) -> str:
        path = match.group(1)
        cur: Any = ctx
        for part in path.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                cur = getattr(cur, part, None)
            if cur is None:
                return ""
        return "\n".join(_render_template(str(item), ctx) for item in cur) if isinstance(cur, list) else str(cur)
    return _TEMPLATE_PATTERN.sub(replace, template)

def _field_default(value: Any) -> Any:
    return value

class _SpecError(ValueError):
    pass


def _validate_json_object_string(value: str) -> str:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as error:
        raise ValueError("value must contain valid JSON") from error
    if not isinstance(parsed, dict):
        raise ValueError("value must contain a JSON object")
    return value

def _resolve_type(
    spec: dict[str, Any],
    model_types: dict[str, type[BaseModel]],
) -> Any:
    t = spec.get("type")
    if t == "str":
        py = str
    elif t == "json_object_str":
        py = Annotated[
            str,
            AfterValidator(_validate_json_object_string),
        ]
    elif t == "bool":
        py = bool
    elif t == "int":
        py = int
    elif t == "float":
        py = float
    elif t == "literal":
        choices = spec.get("choices")
        if not isinstance(choices, list) or not choices:
            raise _SpecError("literal type requires non-empty choices")
        py = Literal[tuple(choices)]  # type: ignore[misc]
    elif t == "list":
        items = spec.get("items")
        if not isinstance(items, dict):
            raise _SpecError("list type requires items spec")
        py = list[_resolve_type(items, model_types)]
    elif t == "json":
        py = Any
    elif t == "ref":
        ref = spec.get("ref")
        if not isinstance(ref, str) or not ref:
            raise _SpecError("ref type requires ref string")
        if ref not in model_types:
            raise _SpecError(f"unknown model ref: {ref}")
        # Use a ForwardRef instead of the (possibly still-empty) shell class.
        # Models that ref a model defined LATER in the JSON would otherwise
        # capture the empty pass-1 shell and silently drop all its fields.
        # Resolved later via model_rebuild with the full namespace.
        py = ForwardRef(ref)
    # 'any' is no longer supported. Only JSON-compatible types are allowed.
    else:
        raise _SpecError(
            f"unsupported field type: {t!r}. Only str, json_object_str, "
            "bool, int, float, literal, list, ref, json allowed."
        )

    if spec.get("optional", False):
        return Optional[py]
    return py

def _build_model_types(models_spec: dict[str, Any]) -> dict[str, type[BaseModel]]:
    if not isinstance(models_spec, dict):
        raise _SpecError("models must be an object")

    built: dict[str, type[BaseModel]] = {}

    # Pass 1: create empty shells so refs can resolve.
    for model_name, spec in models_spec.items():
        if not isinstance(model_name, str) or not model_name:
            continue
        if not isinstance(spec, dict):
            raise _SpecError(f"model {model_name} must be an object")
        built[model_name] = create_model(model_name, __base__=BaseModel)  # type: ignore[assignment]

    # Pass 2: rebuild each model with real fields.
    for model_name, spec in models_spec.items():
        fields_spec = spec.get("fields")
        if not isinstance(fields_spec, dict):
            raise _SpecError(f"model {model_name} fields must be an object")

        annotations: dict[str, Any] = {}
        field_defs: dict[str, Any] = {}
        for field_name, field_spec in fields_spec.items():
            if not isinstance(field_spec, dict):
                raise _SpecError(f"{model_name}.{field_name} must be an object")
            annotations[field_name] = _resolve_type(field_spec, built)
            default_provided = "default" in field_spec
            default_value = _field_default(field_spec.get("default"))

            description = field_spec.get("description")
            if description is not None and not isinstance(description, str):
                description = str(description)

            if default_provided:
                field_defs[field_name] = (annotations[field_name], Field(default_value, description=description))
            else:
                field_defs[field_name] = (annotations[field_name], Field(..., description=description))

        rebuilt = create_model(model_name, __base__=BaseModel, **field_defs)  # type: ignore[arg-type]
        built[model_name] = rebuilt

    # Pass 3: resolve all ForwardRefs now that every model is final in `built`.
    # Order-independent: each model's refs resolve against the full namespace.
    for model_name in built:
        built[model_name].model_rebuild(force=True, _types_namespace=dict(built))

    return built

def _normalize_config_paths(path: str | Path | list) -> list[Path]:
    """Accept a single path or a list/tuple of paths and return list[Path]."""
    if isinstance(path, (str, Path)):
        return [Path(path)]
    if isinstance(path, (list, tuple)):
        if not path:
            raise _SpecError("at least one config path is required")
        return [Path(p) for p in path]
    raise _SpecError("config path must be a str, Path, or list of them")

def _merge_raw_configs(raws: list[Any]) -> dict[str, Any]:
    """Strict disjoint-union merge of several parsed config dicts.

    The ``models``, ``agents`` and ``constants`` sections are merged key by key.
    A key that appears in more than one config is a hard error - every key must
    be defined exactly once across all files. ``version`` is carried from the
    first config that declares it (informational only; not used when building).
    """
    merged: dict[str, Any] = {"models": {}, "agents": {}, "constants": {}}
    version_set = False
    for idx, raw in enumerate(raws):
        if not isinstance(raw, dict):
            raise _SpecError(f"config #{idx} must be a JSON object")
        if not version_set and "version" in raw:
            merged["version"] = raw["version"]
            version_set = True
        for section in ("models", "agents", "constants"):
            section_data = raw.get(section, {})
            if not isinstance(section_data, dict):
                raise _SpecError(f"config #{idx} '{section}' must be an object")
            target = merged[section]
            for key, value in section_data.items():
                if key in target:
                    raise _SpecError(
                        f"duplicate {section} key {key!r} found in multiple config files"
                    )
                target[key] = value
    return merged

class Chivon:
    @classmethod
    def _read_and_merge(cls, path: str | Path | list) -> dict[str, Any]:
        paths = _normalize_config_paths(path)
        raws = [json.loads(Path(p).read_text(encoding="utf-8")) for p in paths]
        return _merge_raw_configs(raws)

    @classmethod
    def build_types_from_file(cls, path: str | Path | list) -> dict[str, type[BaseModel]]:
        raw = cls._read_and_merge(path)
        models_spec = raw.get("models", {})
        return _build_model_types(models_spec)

    def __init__(self) -> None:
        self._loaded = False
        self._agents: dict[str, ChivonAgent] = {}
        self._types: dict[str, type[BaseModel]] = {}
        self._local_tools: dict[str, Any] = {}
        self._mcp_servers: dict[str, Any] = {}
        self._mcp_stack: AsyncExitStack | None = None

    async def __aenter__(self) -> "Chivon":
        # Enter every shared MCP server ONCE for the app lifetime. MCPServerStdio
        # refcounts entry: holding it open here keeps _running_count >= 1, so each
        # agent.run()'s auto-enter/exit just bumps the count (1<->2) instead of
        # respawning the stdio subprocess per run (which raced into BrokenResourceError).
        self._ensure_loaded()
        stack = AsyncExitStack()
        for server in self._mcp_servers.values():
            await stack.enter_async_context(server)
        self._mcp_stack = stack
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._mcp_stack is not None:
            await self._mcp_stack.aclose()
            self._mcp_stack = None

    def _ensure_not_loaded(self) -> None:
        if self._loaded:
            raise RuntimeError("Chivon is already loaded. Create a new instance to load a different config.")

    # --------- Loaders accept a single path/config OR a list of them ---------
    def load_from_file(
        self,
        path,
        model,
        default_model=None,
        mcp_servers=None,
        local_tools=None,
    ):
        self._ensure_not_loaded()
        raw = self._read_and_merge(path)
        self._mcp_servers = mcp_servers or {}
        self._local_tools = local_tools or {}
        self._load_from_raw(raw, model, default_model)  # <- now mcp_servers is ready

    def load_from_string(
        self,
        raw_json,
        model,
        default_model=None,
        mcp_servers=None,
        local_tools=None,
    ):
        self._ensure_not_loaded()
        strings = raw_json if isinstance(raw_json, (list, tuple)) else [raw_json]
        raw = _merge_raw_configs([json.loads(s) for s in strings])
        self._mcp_servers = mcp_servers or {}
        self._local_tools = local_tools or {}
        self._load_from_raw(raw, model, default_model)

    def load_from_json(
        self,
        raw,
        model,
        default_model=None,
        mcp_servers=None,
        local_tools=None,
    ):
        self._ensure_not_loaded()
        raws = list(raw) if isinstance(raw, (list, tuple)) else [raw]
        merged = _merge_raw_configs(raws)
        self._mcp_servers = mcp_servers or {}
        self._local_tools = local_tools or {}
        self._load_from_raw(merged, model, default_model)

    def _load_from_raw(self, raw: Any, model, default_model=None):
        if not isinstance(raw, dict):
            raise _SpecError("agents config must be a JSON object")

        models_spec = raw.get("models", {})
        agents_spec = raw.get("agents", {})
        if not isinstance(agents_spec, dict):
            raise _SpecError("agents must be an object")

        self._types = _build_model_types(models_spec)

        if default_model is None:
            raise _SpecError("default_model must be provided and cannot be None")

        template_ctx = {
            "constants": raw.get("constants", {}),
        }

        for agent_name, spec in agents_spec.items():
            if not isinstance(spec, dict):
                raise _SpecError(f"agent {agent_name} must be an object")

            if default_model is None:
                raise _SpecError(f"default_model must be provided for agent {agent_name}")
            model_obj = default_model

            input_model_name = spec.get("input_model")
            if not isinstance(input_model_name, str) or input_model_name not in self._types:
                raise _SpecError(f"agent {agent_name} has invalid input_model")
            input_type = self._types[input_model_name]

            output_model_name = spec.get("output_model")
            if not isinstance(output_model_name, str) or not output_model_name or output_model_name not in self._types:
                raise _SpecError(f"agent {agent_name} has invalid output_model")
            output_type = self._types[output_model_name]

            system_prompt = spec.get("system_prompt")
            if isinstance(system_prompt, list):
                # New format: list of strings, render each line and join
                rendered_prompt = "\n".join(_render_template(line, template_ctx) for line in system_prompt)
            elif isinstance(system_prompt, str):
                # Old format: single string
                rendered_prompt = _render_template(system_prompt, template_ctx)
            else:
                raise _SpecError(f"agent {agent_name} missing or invalid system_prompt")

            retries = spec.get("retries", 1)
            if not isinstance(retries, int) or retries < 0:
                retries = 1

            _allow_mcp = spec.get("allow_mcp_access", True)
            _mcp_tools = spec.get("mcp_tools")
            _max_tokens = spec.get("max_tokens")
            _model_settings = (
                ModelSettings(max_tokens=_max_tokens)
                if isinstance(_max_tokens, int) and _max_tokens > 0
                else None
            )
            # Per-agent MCP tool exposure:
            #   allow_mcp_access=false           -> no tools
            #   mcp_tools missing/empty          -> all tools from every shared server
            #   mcp_tools=[...] (non-empty)      -> only those tool names (FilteredToolset)
            if _allow_mcp:
                servers = list(self._mcp_servers.values())
                if isinstance(_mcp_tools, list) and _mcp_tools:
                    allowed = set(_mcp_tools)
                    toolsets = [
                        s.filtered(lambda ctx, td, _a=allowed: td.name in _a)
                        for s in servers
                    ]
                else:
                    toolsets = servers
            else:
                toolsets = []

            local_tool_names = spec.get("tools", [])
            if not isinstance(local_tool_names, list):
                raise _SpecError(f"agent {agent_name} tools must be a list")
            tools = []
            for tool_name in local_tool_names:
                if not isinstance(tool_name, str) or tool_name not in self._local_tools:
                    raise _SpecError(
                        f"agent {agent_name} references unknown local tool {tool_name!r}"
                    )
                tools.append(self._local_tools[tool_name])

            agent_obj = Agent(
                model=model,
                output_type=output_type,
                system_prompt=rendered_prompt,
                retries=retries,
                model_settings=_model_settings,
                tools=tools,
                toolsets=toolsets,
            )

            self._agents[str(agent_name)] = ChivonAgent(
                name=str(agent_name),
                agent=agent_obj,
                input_model=input_type,
                output_model=output_type,
            )

        self._loaded = True

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            raise RuntimeError(
                "Chivon is not loaded. Call load_from_file/load_from_string/load_from_json once at startup."
            )

    def agent(self, name: str) -> Agent:
        self._ensure_loaded()
        bundle = self._agents[name]
        # Return a wrapper that pre-normalizes input but uses the original agent (with MCP intact)
        original_agent = bundle.agent
        agent_name = bundle.name

        class _BoundAgent:
            def run_sync(self_, prompt, *args, **kwargs):
                normalized = chivon._normalize_input_text(agent_name, prompt)
                return original_agent.run_sync(normalized, *args, **kwargs)

        return _BoundAgent()

    def output_model(self, name: str) -> type[BaseModel]:
        self._ensure_loaded()
        return self._agents[name].output_model

    def input_model(self, name: str) -> type[BaseModel]:
        self._ensure_loaded()
        return self._agents[name].input_model

    def _normalize_input_text(self, name: str, input_data: Any) -> str:
        bundle = self._agents[name]
        input_type = bundle.input_model

        if isinstance(input_data, str):
            # Detect if input_data is JSON in string form and decode
            try:
                parsed = json.loads(input_data)
                model = input_type.model_validate(parsed)
            except Exception:
                # Treat as raw string TextInput.text
                model = input_type.model_validate({"text": input_data})
        else:
            model = input_type.model_validate(input_data)

        payload = model.model_dump(mode="json")
        # Only short-circuit to plain text for single-field TextInput.
        # If the model has only 'text', serialize as plain text.
        if (
            isinstance(payload, dict)
            and set(payload.keys()) == {"text"}
            and isinstance(payload.get("text"), str)
        ):
            return payload["text"]

        schema = input_type.model_json_schema()
        return json.dumps({"__schema": schema, "__data": payload}, ensure_ascii=False)

    def run_sync(self, name: str, input_data: Any, *, message_history: list | None = None) -> Any:
        """
        Validate/normalize input using agent's input_model, then run the underlying Agent.
        Returns the raw AgentResult from pydantic_ai (same as Agent.run_sync).
        """
        self._ensure_loaded()
        prompt = self._normalize_input_text(name, input_data)
        agent_obj = self._agents[name].agent
        if message_history:
            return agent_obj.run_sync(prompt, message_history=message_history)
        return agent_obj.run_sync(prompt)

    async def run_async(self, name: str, input_data: Any, *, message_history: list | None = None) -> Any:
        """
        Async version of run_sync. Use from async endpoints to avoid event loop conflicts.
        Returns the raw AgentResult from pydantic_ai (same as Agent.run).
        """
        self._ensure_loaded()
        prompt = self._normalize_input_text(name, input_data)
        agent_obj = self._agents[name].agent
        if message_history:
            return await agent_obj.run(prompt, message_history=message_history)
        return await agent_obj.run(prompt)

    async def run_async_multimodal(
        self,
        name: str,
        input_data: Any,
        images: list[tuple[bytes, str]],
    ) -> Any:
        """
        Async multimodal run - attaches image BinaryContent objects alongside the text prompt.
        images: list of (bytes, media_type) tuples.
        """
        self._ensure_loaded()
        prompt = self._normalize_input_text(name, input_data)
        agent_obj = self._agents[name].agent
        from pydantic_ai import BinaryContent
        user_message: list = [prompt]
        for img_bytes, media_type in images:
            user_message.append(BinaryContent(data=img_bytes, media_type=media_type))
        return await agent_obj.run(user_message)

    def run_sync_multimodal(
        self,
        name: str,
        input_data: Any,
        images: list[tuple[bytes, str]],
    ) -> Any:
        """
        Sync multimodal run - attaches image BinaryContent objects alongside the text prompt.
        images: list of (bytes, media_type) tuples.
        """
        self._ensure_loaded()
        prompt = self._normalize_input_text(name, input_data)
        agent_obj = self._agents[name].agent
        from pydantic_ai import BinaryContent
        user_message: list = [prompt]
        for img_bytes, media_type in images:
            user_message.append(BinaryContent(data=img_bytes, media_type=media_type))
        return agent_obj.run_sync(user_message)

    def type(self, model_name: str) -> type[BaseModel]:
        self._ensure_loaded()
        return self._types[model_name]

    @property
    def agents(self) -> dict[str, ChivonAgent]:
        self._ensure_loaded()
        return dict(self._agents)

    @property
    def types(self) -> dict[str, type[BaseModel]]:
        self._ensure_loaded()
        return dict(self._types)

chivon = Chivon()