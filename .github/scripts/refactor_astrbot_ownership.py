from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8", newline="\n")


def once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, got {count}")
    return text.replace(old, new, 1)


def between(text: str, start: str, end: str, replacement: str, label: str) -> str:
    i = text.find(start)
    j = text.find(end, i + 1) if i >= 0 else -1
    if i < 0 or j < 0:
        raise RuntimeError(f"{label}: markers not found")
    return text[:i] + replacement + text[j:]


# ---- Generation Flow: AstrBot owns Agent/ToolSet/prompt/input -----------------
path = "plugins/astrbot_plugin_contract_generation_flow/main.py"
s = read(path)
s = once(s, "import asyncio\nimport json\nimport uuid\n", "import asyncio\nimport inspect\nimport json\nimport uuid\n", "inspect import")
s = once(
    s,
    "from astrbot.core.agent.tool import FunctionTool\nfrom astrbot.core.astr_agent_tool_exec import FunctionToolExecutor\n",
    "from astrbot.core.agent.mcp_client import MCPTool\nfrom astrbot.core.agent.tool import FunctionTool\n",
    "executor import",
)
s = once(
    s,
    'DOCUMENT_SPEC_SKILL_NAME = "contract-document-specification"\nSKILL_RUNTIME_BEGIN = "<contract_builder_skill_runtime>"\nSKILL_RUNTIME_END = "</contract_builder_skill_runtime>"\nMAX_BOUND_SKILL_CHARS = 128000\n',
    'DOCUMENT_SPEC_SKILL_NAME = "contract-document-specification"\nMAX_BOUND_SKILL_CHARS = 128000\nINTERNAL_TOOL_CALL_TIMEOUT_SECONDS = 120\nBUILDER_BOUND_TOOL_NAMES = (\n    "read_bound_skill",\n    "find_generation_assets",\n    "read_generation_asset",\n    "find_similar_contracts",\n    "read_reference_contract",\n    "read_latest_contract_draft",\n    "read_contract_draft",\n    "generate_and_publish_contract",\n)\n',
    "runtime constants",
)
s = once(
    s,
    "def _resolve_registered_tool(context: Context, name: str) -> FunctionTool | None:\n    return context.get_llm_tool_manager().get_full_tool_set().get_tool(name)\n",
    "def _resolve_registered_tool(context: Context, name: str) -> FunctionTool | None:\n    # Internal composition resolves the raw registered implementation. AstrBot\n    # remains responsible for exposing and binding public tools to agents.\n    return context.get_llm_tool_manager().get_func(name)\n",
    "raw tool resolution",
)

invoke = '''class _EventToolContext:
    \"\"\"Minimal context for deterministic composition of known registered tools.\"\"\"

    class _EventView:
        def __init__(self, event: AstrMessageEvent) -> None:
            self.event = event

    def __init__(self, event: AstrMessageEvent) -> None:
        self.context = self._EventView(event)
        self.tool_call_timeout = INTERNAL_TOOL_CALL_TIMEOUT_SECONDS


async def _invoke_registered_tool(
    tool: FunctionTool,
    context: _EventToolContext,
    *,
    side_effecting: bool = False,
    **tool_args: Any,
) -> Any:
    \"\"\"Call only a known local plugin handler or MCPTool for business composition.\"\"\"
    try:
        if tool.handler is not None:
            result = tool.handler(context.context.event, **tool_args)
            if inspect.isasyncgen(result):
                last: Any = None
                async for item in result:
                    if item is not None:
                        last = item
                return last
            if inspect.isawaitable(result):
                return await result
            return result
        if isinstance(tool, MCPTool):
            return await tool.call(context, **tool_args)
        logger.error(
            \"Contract generation flow: unsupported internal tool implementation: %s\",
            getattr(tool, \"name\", type(tool).__name__),
        )
        return {
            \"isError\": True,
            \"error\": \"unsupported internal tool implementation\",
            \"retry_safe\": not side_effecting,
            \"commit_unknown\": side_effecting,
        }
    except asyncio.CancelledError:
        logger.error(
            \"Contract generation flow: registered tool %s was cancelled during execution\",
            getattr(tool, \"name\", type(tool).__name__),
        )
        raise
    except Exception:
        logger.exception(
            \"Contract generation flow: registered tool %s raised during execution\",
            getattr(tool, \"name\", type(tool).__name__),
        )
        return {
            \"isError\": True,
            \"error\": \"registered tool execution failed\",
            \"retry_safe\": not side_effecting,
            \"commit_unknown\": side_effecting,
        }

'''
s = between(s, "async def _invoke_registered_tool(\n", "def _scalar(value: str) -> str:\n", invoke, "internal invocation")

helper_marker = "\n\ndef _skill_id_matches_logical_name"
tool_helper = '''

def _builder_bound_tool_names(context: Context) -> list[str]:
    persona_manager = getattr(context, \"persona_manager\", None)
    if persona_manager is None:
        return []
    persona = persona_manager.get_persona_v3_by_id(BUILDER_PERSONA_ID)
    if not isinstance(persona, dict):
        return []
    raw = persona.get(\"tools\")
    if not isinstance(raw, list):
        return []
    names: list[str] = []
    for item in raw:
        name = str(item or \"\").strip()
        if name and name not in names:
            names.append(name)
    return names
'''
s = once(s, helper_marker, tool_helper + helper_marker, "Builder tool binding helper")

idem = '''        if not skill.local_exists:
            return _normalized_tool_failure(
                failure_stage=\"skill_grounding\",
                error=f\"Skill {skill_name} 仅存在于隔离运行时，当前受限读取入口无法读取。\",
            )
'''
idem2 = idem + '''        if (
            _skill_id_matches_logical_name(skill.name, DOCUMENT_SPEC_SKILL_NAME)
            and event.get_extra(\"contract_generation_document_spec_loaded\", False)
            and str(event.get_extra(\"contract_generation_document_spec_skill_id\", \"\") or \"\").strip() == skill.name
        ):
            return _tool_json(
                {
                    \"success\": True,
                    \"status\": \"already_grounded\",
                    \"skill\": DOCUMENT_SPEC_SKILL_NAME,
                    \"runtime_id\": skill.name,
                    \"retry_safe\": True,
                }
            )
'''
s = once(s, idem, idem2, "Skill grounding idempotence")

# Draft readers are already normal DOCX Generator tools; do not shadow them.
s = between(
    s,
    "class _DynamicRegisteredTool(FunctionTool):\n",
    "\n\nclass _BoundCorpusTool(FunctionTool):\n",
    "class _BoundCorpusTool(FunctionTool):\n",
    "remove draft pass-through class",
)

skill_state = '''    def _prepare_builder_skill_state(
        self,
        event: AstrMessageEvent,
    ) -> list[str]:
        bound_names, skill_infos, missing_skills = self._bound_skill_infos(event)
        runtime_missing: list[str] = []
        document_spec_bindings = [
            name for name in bound_names
            if _skill_id_matches_logical_name(name, DOCUMENT_SPEC_SKILL_NAME)
        ]
        if not document_spec_bindings:
            runtime_missing.append(\"builder_document_spec_binding\")
        elif len(document_spec_bindings) > 1:
            runtime_missing.append(\"builder_document_spec_binding_ambiguous\")
        readable_skill_ids = {skill.name for skill in skill_infos if skill.local_exists}
        resolved_id = document_spec_bindings[0] if len(document_spec_bindings) == 1 else \"\"
        available = bool(resolved_id and resolved_id in readable_skill_ids)
        event.set_extra(\"contract_generation_document_spec_available\", available)
        event.set_extra(\"contract_generation_document_spec_skill_id\", resolved_id if available else \"\")
        if len(document_spec_bindings) == 1 and not available:
            runtime_missing.append(\"builder_document_spec_skill\")
        for name in missing_skills:
            marker = f\"builder_skill:{name}\"
            if marker not in runtime_missing:
                runtime_missing.append(marker)
        return runtime_missing

'''
s = between(
    s,
    "    @staticmethod\n    def _restricted_skill_runtime_block",
    "    def _build_runtime_tools",
    skill_state + "    def _build_runtime_tools",
    "remove dynamic Skill inventory/input injection",
)
s = once(s, "    def _build_runtime_tools(self) -> list[FunctionTool]:\n", "    def _build_business_tools(self) -> list[FunctionTool]:\n", "business tool builder rename")

old_drafts = '''        tools.extend(
            [
                _DynamicRegisteredTool(
                    context=self._context,
                    source_name=\"read_latest_contract_draft\",
                    public_name=\"read_latest_contract_draft\",
                    description=(
                        \"一次取得当前会话最近成功交付合同草稿的元数据和首段正文。\"
                        \"修改上一版时优先调用。\"
                    ),
                    parameters=READ_LATEST_DRAFT_PARAMETERS,
                ),
                _DynamicRegisteredTool(
                    context=self._context,
                    source_name=\"read_contract_draft\",
                    public_name=\"read_contract_draft\",
                    description=\"仅在上一版草稿返回 next_offset 时继续读取后续正文。\",
                    parameters=READ_DRAFT_PARAMETERS,
                ),
                _GenerateAndPublishTool(self._context),
            ]
        )
'''
s = once(s, old_drafts, "        tools.append(_GenerateAndPublishTool(self._context))\n", "remove draft wrapper construction")
s = once(
    s,
    "        registered = self._context.get_llm_tool_manager().get_full_tool_set()\n        missing: list[str] = []\n        for name in RUNTIME_SOURCE_NAMES:\n            tool = registered.get_tool(name)\n",
    "        manager = self._context.get_llm_tool_manager()\n        missing: list[str] = []\n        for name in RUNTIME_SOURCE_NAMES:\n            tool = manager.get_func(name)\n",
    "runtime diagnostics",
)

old_prompt = '''    @staticmethod
    def _builder_prompt_compatible(agent: Any) -> bool:
        prompt = str(getattr(agent, \"instructions\", \"\") or \"\").strip()
        return bool(prompt and BUILDER_PROTOCOL_MARKER in prompt)
'''
new_prompt = '''    def _builder_prompt_compatible(self) -> bool:
        persona_manager = getattr(self._context, \"persona_manager\", None)
        if persona_manager is None:
            return False
        persona = persona_manager.get_persona_v3_by_id(BUILDER_PERSONA_ID)
        if not isinstance(persona, dict):
            return False
        prompt = str(persona.get(\"prompt\") or persona.get(\"system_prompt\") or \"\").strip()
        return bool(prompt and BUILDER_PROTOCOL_MARKER in prompt)
'''
s = once(s, old_prompt, new_prompt, "Persona prompt validation")

handlers = '''    def _validate_builder_runtime(
        self,
        event: AstrMessageEvent,
    ) -> tuple[list[str], list[str]]:
        try:
            missing = self._prepare_builder_skill_state(event)
            event.set_extra(\"contract_generation_skill_runtime_error\", \"\")
        except Exception:
            logger.exception(\"Contract generation flow: failed to inspect Builder Skill binding\")
            event.set_extra(\"contract_generation_document_spec_available\", False)
            event.set_extra(\"contract_generation_skill_runtime_error\", \"builder skill binding inspection failed\")
            missing = [\"builder_skill_runtime\", \"builder_document_spec_skill\"]
        bound_tools = _builder_bound_tool_names(self._context)
        for name in BUILDER_BOUND_TOOL_NAMES:
            if name not in bound_tools:
                missing.append(f\"builder_tool_binding:{name}\")
        manager = self._context.get_llm_tool_manager()
        for name in BUILDER_BOUND_TOOL_NAMES:
            tool = manager.get_func(name)
            if tool is None or not getattr(tool, \"active\", True):
                missing.append(f\"builder_tool:{name}\")
        diagnostics = self._runtime_diagnostics(event)
        event.set_extra(\"contract_generation_builder_runtime_optional_missing\", diagnostics)
        event.set_extra(ASSET_CORPUS_EVENT_KEY, self.asset_corpus_slug)
        if not self._builder_prompt_compatible():
            missing.append(\"builder_persona_protocol_v7\")
        deduped: list[str] = []
        for item in missing:
            if item not in deduped:
                deduped.append(item)
        return list(BUILDER_BOUND_TOOL_NAMES), deduped

    async def _call_business_tool(self, event: AstrMessageEvent, name: str, **tool_args: Any) -> Any:
        if event.get_extra(\"contract_generation_terminal_failure\", False):
            return _normalized_tool_failure(
                failure_stage=\"generation_terminal\",
                error=str(event.get_extra(\"contract_generation_terminal_failure_reason\", \"\") or \"当前 generation 已进入 terminal 状态。\"),
                retry_safe=False,
                handoff_terminal=True,
                write_started=bool(event.get_extra(\"contract_generation_write_stage\", \"\")),
            )
        tool = self._business_tools.get(name)
        if tool is None:
            return _normalized_tool_failure(failure_stage=\"runtime_tool\", error=f\"业务工具 {name} 未注册。\", retry_safe=False, handoff_terminal=True)
        return await tool.call(_EventToolContext(event), **tool_args)

    @filter.llm_tool(name=\"read_bound_skill\")
    async def read_bound_skill(self, event: AstrMessageEvent, skill_name: str) -> Any:
        \"\"\"读取 Builder 当前实际绑定的指定 Skill。\"\"\"
        return await self._call_business_tool(event, \"read_bound_skill\", skill_name=skill_name)

    @filter.llm_tool(name=\"find_generation_assets\")
    async def find_generation_assets(self, event: AstrMessageEvent, query: str, limit: int = SEARCH_DEFAULT_LIMIT, granularity: str = \"passage\") -> Any:
        \"\"\"在受限生成资产 Corpus 中检索合同模板、参数或规则。\"\"\"
        return await self._call_business_tool(event, \"find_generation_assets\", query=query, limit=limit, granularity=granularity)

    @filter.llm_tool(name=\"read_generation_asset\")
    async def read_generation_asset(self, event: AstrMessageEvent, document_slug: str, char_offset: int = 0, max_chars: int = TEMPLATE_READ_DEFAULT_CHARS, use_as_template: bool = False) -> Any:
        \"\"\"读取本轮生成资产候选；模板绑定必须来自本轮搜索证据。\"\"\"
        return await self._call_business_tool(event, \"read_generation_asset\", document_slug=document_slug, char_offset=char_offset, max_chars=max_chars, use_as_template=use_as_template)

    @filter.llm_tool(name=\"find_similar_contracts\")
    async def find_similar_contracts(self, event: AstrMessageEvent, query: str, limit: int = SEARCH_DEFAULT_LIMIT, granularity: str = \"passage\") -> Any:
        \"\"\"在当前 handoff 绑定的历史合同 Corpus 中检索相似合同。\"\"\"
        return await self._call_business_tool(event, \"find_similar_contracts\", query=query, limit=limit, granularity=granularity)

    @filter.llm_tool(name=\"read_reference_contract\")
    async def read_reference_contract(self, event: AstrMessageEvent, document_slug: str, char_offset: int = 0, max_chars: int = REFERENCE_READ_DEFAULT_CHARS) -> Any:
        \"\"\"读取本轮历史合同候选正文。\"\"\"
        return await self._call_business_tool(event, \"read_reference_contract\", document_slug=document_slug, char_offset=char_offset, max_chars=max_chars)

    @filter.llm_tool(name=\"generate_and_publish_contract\")
    async def generate_and_publish_contract(self, event: AstrMessageEvent, document_title: str, document_markdown: str, generation_basis: str, output_filename: str = \"\", render_profile: str = \"standard_contract\", source_draft_id: str = \"\") -> Any:
        \"\"\"一次完成 DOCX 生成、HTTPS 发布和成功草稿持久化。\"\"\"
        return await self._call_business_tool(event, \"generate_and_publish_contract\", document_title=document_title, document_markdown=document_markdown, generation_basis=generation_basis, output_filename=output_filename, render_profile=render_profile, source_draft_id=source_draft_id)

'''
s = between(s, "    async def _ensure_runtime_tools(\n", "    async def _send_progress_once", handlers + "    async def _send_progress_once", "replace Agent ToolSet injection")

s = once(
    s,
    "        self._runtime_lock = asyncio.Lock()\n        self._runtime_tools = self._build_runtime_tools()\n",
    "        self._business_tools = {tool.name: tool for tool in self._build_business_tools()}\n",
    "constructor ownership",
)
s = s.replace("Contract generation flow 0.7.4 initialized: asset_corpus=%s", "Contract generation flow 0.8.0 initialized: asset_corpus=%s")

old_hook = '''        parsed_input, parse_error = self._parse_generation_input(tool_args.get(\"input\"))
        event.set_extra(\"contract_generation_task\", True)
        self._reset_generation_state(event)
        self._apply_generation_policy(event, parsed_input, parse_error)
        tool_args[\"background_task\"] = False

        agent = getattr(tool, \"agent\", None)
        if agent is None:
            runtime_tools, missing, runtime_block = [], [\"builder_agent\"], \"\"
        else:
            runtime_tools, missing, runtime_block = await self._ensure_runtime_tools(agent, event)

        if runtime_block:
            self._prepend_skill_runtime_input(tool_args, runtime_block)
            event.set_extra(\"contract_generation_skill_runtime_injected\", True)

        event.set_extra(\"contract_generation_builder_runtime_tools\", runtime_tools)
        event.set_extra(\"contract_generation_builder_runtime_missing\", missing)
'''
new_hook = '''        parsed_input, parse_error = self._parse_generation_input(tool_args.get(\"input\"))
        event.set_extra(\"contract_generation_task\", True)
        self._reset_generation_state(event)
        self._apply_generation_policy(event, parsed_input, parse_error)
        if not event.get_extra(\"contract_generation_policy_verified\", False):
            _mark_terminal_failure(
                event,
                str(event.get_extra(\"contract_generation_policy_error\", \"\") or \"生成策略无效。\"),
                stage=\"generation_policy\",
                commit_unknown=False,
            )
        runtime_tools, missing = self._validate_builder_runtime(event)
        event.set_extra(\"contract_generation_builder_runtime_tools\", runtime_tools)
        event.set_extra(\"contract_generation_builder_runtime_missing\", missing)
'''
s = once(s, old_hook, new_hook, "handoff hook")
s = s.replace('                "document_spec_skill_id=%s document_spec_loaded=%s "\n                "skill_runtime_injected=%s tools=%s",', '                "document_spec_skill_id=%s document_spec_loaded=%s tools=%s",')
s = s.replace('                event.get_extra("contract_generation_document_spec_loaded", False),\n                event.get_extra("contract_generation_skill_runtime_injected", False),\n                runtime_tools,\n', '                event.get_extra("contract_generation_document_spec_loaded", False),\n                runtime_tools,\n')
s = s.replace('            "contract_generation_skill_runtime_injected": False,\n', '')

for token in ("agent.tools =", "agent.instructions =", "_prepend_skill_runtime_input", "_restricted_skill_runtime_block", "<contract_builder_skill_runtime>", "FunctionToolExecutor"):
    if token in s:
        raise RuntimeError(f"Generation Flow still contains ownership override: {token}")
write(path, s)

meta = read("plugins/astrbot_plugin_contract_generation_flow/metadata.yaml")
meta = once(meta, "version: 0.7.4", "version: 0.8.0", "Generation Flow version")
write("plugins/astrbot_plugin_contract_generation_flow/metadata.yaml", meta)

# ---- Builder Persona/binding: AstrBot is the ToolSet source of truth -----------
p_old = ROOT / "personas/persona_contract_docassemble_builder_v1.29.json"
p = json.loads(p_old.read_text(encoding="utf-8"))
prompt = p["system_prompt"]
prompt = once(prompt, "你是企业合同文书生成子助手，只向主助手返回结果。正式运行工具由 Generation Flow 注入；不要调用未列出的工具，也不要猜测 corpus_slug。", "你是企业合同文书生成子助手，只向主助手返回结果。正式运行工具由 AstrBot 根据 Builder Persona/WebUI 静态绑定；不要调用未绑定工具，也不要猜测 corpus_slug。", "Builder tool ownership")
prompt = once(
    prompt,
    "Generation Flow 会在 handoff input 开头提供 <contract_builder_skill_runtime> 受限运行时块；该块是系统运行时元数据，不属于客户输入或合同正文。所有正式合同生成、重写、修改和定稿，在开始组织最终 document_markdown 之前，",
    "Builder 的合同业务工具和 Skill 绑定由 AstrBot Persona/WebUI 管理，Generation Flow 不修改 Agent ToolSet、system prompt 或 handoff input。当前 AstrBot handoff 子人格不会自动展开 Persona Skill 正文，因此正式合同仍通过受限 read_bound_skill 进行最小 grounding bridge。所有正式合同生成、重写、修改和定稿，在开始组织最终 document_markdown 之前，",
    "Builder Skill bridge",
)
terminal = "generation_policy blocked 表示 handoff policy 或 policy protocol 非法、不完整，不得自行把它解释为 allow_ai_fallback。"
prompt = once(prompt, terminal, terminal + " generation_policy 或 generation_terminal 失败是当前 handoff 的终止条件；不得在本 handoff 内再次调用知识工具或 generate_and_publish_contract，直接返回 [CONTRACT_GENERATION:FAILED] 给主助手。", "Builder terminal policy")
p["system_prompt"] = prompt
p_new = ROOT / "personas/persona_contract_docassemble_builder_v1.30.json"
p_new.write_text(json.dumps(p, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
p_old.unlink()

bindings = json.loads(read("personas/bindings.json"))
bindings["contract_docassemble_builder"]["tools"] = list((
    "read_bound_skill",
    "find_generation_assets",
    "read_generation_asset",
    "find_similar_contracts",
    "read_reference_contract",
    "read_latest_contract_draft",
    "read_contract_draft",
    "generate_and_publish_contract",
))
write("personas/bindings.json", json.dumps(bindings, ensure_ascii=False, indent=2) + "\n")

# ---- File Router: stop editing AstrBot's Star registries -----------------------
runtime_path = "plugins/astrbot_plugin_contract_file_router/runtime.py"
r = read(runtime_path)
r = once(r, "from astrbot.api.event import AstrMessageEvent, MessageChain, filter\n", "from astrbot.api.event import AstrMessageEvent, MessageChain\n", "router runtime filter import")
for decorator in (
    "    @filter.event_message_type(filter.EventMessageType.ALL, priority=1000)\n",
    "    @filter.on_llm_request(priority=1000)\n",
    "    @filter.after_message_sent(priority=-999)\n",
):
    r = once(r, decorator, "", "router runtime decorator")
write(runtime_path, r)

main_path = "plugins/astrbot_plugin_contract_file_router/main.py"
r = read(main_path)
r = once(r, "from astrbot.core.star import star_map, star_registry\nfrom astrbot.core.star.star_handler import star_handlers_registry\n\n", "", "router private registry imports")
i = r.find("_RUNTIME_MODULE = RuntimeContractFileRouter.__module__\n")
j = r.find("_STAGED_TEXT_EVENT_KEY =", i)
if i < 0 or j < 0:
    raise RuntimeError("router registry repair block not found")
r = r[:i] + r[j:]
r = r.replace("Contract file router 0.5.7 initialized", "Contract file router 0.5.8 initialized")
for token in ("star_map", "star_registry", "star_handlers_registry", "_remove_runtime_registrations"):
    if token in r:
        raise RuntimeError(f"File Router still edits AstrBot registry: {token}")
write(main_path, r)

meta = read("plugins/astrbot_plugin_contract_file_router/metadata.yaml")
meta = once(meta, "version: 0.5.7", "version: 0.5.8", "File Router version")
write("plugins/astrbot_plugin_contract_file_router/metadata.yaml", meta)

# ---- Permanent ownership regression check --------------------------------------
guard = '''from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = {
    "plugins/astrbot_plugin_contract_generation_flow/main.py": (
        "agent.tools =", "agent.instructions =", "_prepend_skill_runtime_input",
        "<contract_builder_skill_runtime>", "FunctionToolExecutor",
    ),
    "plugins/astrbot_plugin_contract_file_router/main.py": (
        "star_map", "star_registry", "star_handlers_registry", "_remove_runtime_registrations",
    ),
}
errors = []
for relative, tokens in FORBIDDEN.items():
    text = (ROOT / relative).read_text(encoding="utf-8")
    for token in tokens:
        if token in text:
            errors.append(f"{relative}: forbidden AstrBot ownership override: {token}")

bindings = json.loads((ROOT / "personas/bindings.json").read_text(encoding="utf-8"))
actual = set(bindings.get("contract_docassemble_builder", {}).get("tools", []))
expected = {
    "read_bound_skill", "find_generation_assets", "read_generation_asset",
    "find_similar_contracts", "read_reference_contract", "read_latest_contract_draft",
    "read_contract_draft", "generate_and_publish_contract",
}
if actual != expected:
    errors.append(f"Builder tool binding mismatch: expected={sorted(expected)} actual={sorted(actual)}")
if errors:
    raise SystemExit("\n".join(errors))
print("AstrBot ownership validation passed.")
'''
write("scripts/validate_astrbot_ownership.py", guard)

# ---- Docs/version baselines ------------------------------------------------------
docs = (
    "README.md",
    "VERSIONS.md",
    "docs/architecture/ai-docx-generation.md",
    "docs/architecture/system-context.md",
    "docs/deployment/persona-manual-config.md",
    "plugins/astrbot_plugin_contract_generation_flow/README.md",
)
for doc in docs:
    t = read(doc)
    t = t.replace("Generation Flow 0.7.4", "Generation Flow 0.8.0")
    t = t.replace("astrbot_plugin_contract_generation_flow: 0.7.4", "astrbot_plugin_contract_generation_flow: 0.8.0")
    t = t.replace("astrbot_plugin_contract_generation_flow     0.7.4", "astrbot_plugin_contract_generation_flow     0.8.0")
    t = t.replace("Builder 1.29", "Builder 1.30")
    t = t.replace("contract_docassemble_builder       1.29", "contract_docassemble_builder       1.30")
    t = t.replace("astrbot_plugin_contract_file_router: 0.5.7", "astrbot_plugin_contract_file_router: 0.5.8")
    t = t.replace("astrbot_plugin_contract_file_router         0.5.7", "astrbot_plugin_contract_file_router         0.5.8")
    write(doc, t.rstrip() + "\n")

arch_path = "docs/architecture/system-context.md"
arch = read(arch_path)
note = '''\n\n## AstrBot runtime ownership boundary\n\nContractBot 插件不接管 AstrBot 的 Agent runtime。Builder 的 system prompt、ToolSet 和 Persona Skill 绑定由 AstrBot Persona/WebUI 管理；Generation Flow 只注册合同业务工具并校验绑定，不修改 `agent.tools`、`agent.instructions` 或 handoff `input`。\n\n当前保留的 `read_bound_skill` 是最小兼容桥：AstrBot handoff 子人格尚未自动展开 Persona Skill 正文，因此该工具只验证 Builder 当前真实 Skill 绑定并读取对应 `SKILL.md`。它不生成动态 Skill inventory、不注入 handoff prompt，也不开放任意文件读取。同一 handoff 对同一文档规范 Skill 的重复读取返回 `already_grounded`。\n\nFile Router 的事件处理只通过 `main.py` 中的官方 decorators 注册；实现基类不再直接修改 `star_map`、`star_registry` 或 `star_handlers_registry`。`scripts/validate_astrbot_ownership.py` 用于防止这两类 ownership override 回归。\n\n本轮同时审计 Handoff Policy、DOC Preconverter、DOCX Generator、Download Delivery、OpenContracts Gateway 和 WeCom Result Guard：这些组件通过 AstrBot 官方事件/工具 hooks 执行业务策略、消息预处理、工具实现或结果规范化，没有发现同类 Agent/Persona/ToolSet/Star registry 接管。\n'''
if "## AstrBot runtime ownership boundary" not in arch:
    arch = arch.rstrip() + note
write(arch_path, arch.rstrip() + "\n")

fr = read("plugins/astrbot_plugin_contract_generation_flow/README.md")
note = '''\n\n## Runtime ownership\n\n0.8.0 起，Generation Flow 不再在 handoff hook 中覆盖 `agent.tools`，不修改共享 `agent.instructions`，也不向 `transfer_to_docassemble_builder.input` 注入 Skill runtime 文本。公开 Builder 工具由 AstrBot 正常注册，并通过 Persona/WebUI 静态绑定；Flow 只读取 Persona/Skill/Tool 绑定做 fail-closed 校验。\n\n`read_latest_contract_draft` 与 `read_contract_draft` 直接使用 DOCX Generator 已注册的只读工具；Generation Flow 不再创建同名 pass-through wrapper。`generate_and_publish_contract` 仍是唯一正式写组合入口，底层 `generate_contract_docx`、`publish_contract_download` 和 `finalize_contract_draft` 不绑定给 Builder。\n'''
if "## Runtime ownership" not in fr:
    fr = fr.rstrip() + note
write("plugins/astrbot_plugin_contract_generation_flow/README.md", fr.rstrip() + "\n")

readme = read("README.md")
note = '''\n\n### AstrBot ownership boundary\n\nGeneration Flow 0.8.0 不再作为第二套 Agent runtime：不覆盖 Builder ToolSet、不改 system prompt、不包装 handoff input。Builder 的 8 个允许工具必须在 AstrBot Persona/WebUI 中静态绑定；Flow 只负责合同生成证据、状态机和写安全门槛。File Router 0.5.8 同时移除了对 AstrBot Star 全局注册表的直接修改。\n'''
if "### AstrBot ownership boundary" not in readme:
    readme = readme.rstrip() + note
write("README.md", readme.rstrip() + "\n")

versions = read("VERSIONS.md")
versions = versions.replace("contract_docassemble_builder: 1.29", "contract_docassemble_builder: 1.30")
versions = versions.replace("astrbot_plugin_contract_file_router: 0.5.7", "astrbot_plugin_contract_file_router: 0.5.8")
versions = versions.replace("astrbot_plugin_contract_generation_flow: 0.7.4", "astrbot_plugin_contract_generation_flow: 0.8.0")
write("VERSIONS.md", versions.rstrip() + "\n")

print("AstrBot runtime ownership refactor applied.")
