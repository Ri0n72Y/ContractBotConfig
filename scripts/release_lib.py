"""Deterministic packaging helpers for ContractBot releases."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

EXCLUDED_NAMES = {".DS_Store", "__pycache__", ".git"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".log", ".tmp"}
ZIP_TIMESTAMP = (2026, 1, 1, 0, 0, 0)
PERSONA_FILENAME_RE = re.compile(
    r"^persona_(?P<persona_id>.+)_v(?P<version>\d+(?:\.\d+)*)\.json$"
)


@dataclass(frozen=True)
class Artifact:
    category: str
    name: str
    version: str | None
    source: str
    file: str
    size_bytes: int
    sha256: str


def included_files(directory: Path) -> Iterable[Path]:
    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(directory)
        if any(part in EXCLUDED_NAMES for part in relative.parts):
            continue
        if path.suffix.lower() in EXCLUDED_SUFFIXES:
            continue
        yield path


def write_zip(source: Path, output: Path, include_root: bool = True) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        output,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for path in included_files(source):
            relative = path.relative_to(source)
            archive_name = Path(source.name) / relative if include_root else relative
            info = zipfile.ZipInfo(str(archive_name).replace("\\", "/"))
            info.date_time = ZIP_TIMESTAMP
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def plugin_version(plugin: Path) -> str:
    metadata = plugin / "metadata.yaml"
    if not metadata.is_file() or not (plugin / "main.py").is_file():
        raise ValueError(f"Invalid AstrBot plugin directory: {plugin}")
    match = re.search(
        r"(?m)^version:\s*[\"']?([^\s\"']+)",
        metadata.read_text(encoding="utf-8"),
    )
    if not match:
        raise ValueError(f"Missing version in {metadata}")
    return match.group(1)


def skill_versions(root: Path) -> dict[str, str]:
    path = root / "VERSIONS.md"
    if not path.is_file():
        return {}
    versions: dict[str, str] = {}
    active = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() == "## Skills":
            active = True
            continue
        if active and line.startswith("## "):
            break
        if active and (match := re.match(r"-\s+([^:]+):\s*(\S+)", line.strip())):
            versions[match.group(1).strip()] = match.group(2).strip()
    return versions


def display_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def artifact(
    root: Path,
    category: str,
    name: str,
    version: str | None,
    source: Path,
    output: Path,
) -> Artifact:
    return Artifact(
        category=category,
        name=name,
        version=version,
        source=display_path(source, root),
        file=display_path(output, root),
        size_bytes=output.stat().st_size,
        sha256=sha256(output),
    )


def load_persona_bindings(personas: Path) -> dict[str, dict[str, list[str]]]:
    path = personas / "bindings.json"
    if not path.is_file():
        raise ValueError(f"Missing Persona bindings file: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Persona bindings must be a JSON object: {path}")

    normalized: dict[str, dict[str, list[str]]] = {}
    for persona_id, raw in payload.items():
        if not isinstance(raw, dict):
            raise ValueError(f"Invalid bindings for Persona {persona_id}")
        tools = raw.get("tools")
        skills = raw.get("skills")
        if not isinstance(tools, list) or not all(
            isinstance(item, str) and item.strip() for item in tools
        ):
            raise ValueError(f"Invalid tools binding for Persona {persona_id}")
        if not isinstance(skills, list) or not all(
            isinstance(item, str) and item.strip() for item in skills
        ):
            raise ValueError(f"Invalid skills binding for Persona {persona_id}")
        normalized[str(persona_id)] = {
            "tools": [item.strip() for item in tools],
            "skills": [item.strip() for item in skills],
        }
    return normalized


def load_persona_source(path: Path) -> tuple[str, str, str, list[Any]]:
    match = PERSONA_FILENAME_RE.match(path.name)
    if not match:
        raise ValueError(f"Invalid Persona filename: {path.name}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid Persona JSON object: {path}")

    persona_id = str(payload.get("persona_id") or "").strip()
    expected_id = match.group("persona_id")
    if persona_id != expected_id:
        raise ValueError(
            f"Persona id mismatch: filename={expected_id} payload={persona_id or '<empty>'}"
        )
    system_prompt = str(payload.get("system_prompt") or "").strip()
    if not system_prompt:
        raise ValueError(f"Persona system_prompt is empty: {path}")
    begin_dialogs = payload.get("begin_dialogs", [])
    if not isinstance(begin_dialogs, list):
        raise ValueError(f"Persona begin_dialogs must be a list: {path}")
    return persona_id, match.group("version"), system_prompt, begin_dialogs


def render_persona_markdown(
    persona_id: str,
    version: str,
    system_prompt: str,
    begin_dialogs: list[Any],
    tools: list[str],
    skills: list[str],
) -> str:
    tool_lines = ["tools:", *[f"  - {name}" for name in tools]] if tools else ["tools: []"]
    skill_lines = (
        ["skills:", *[f"  - {name}" for name in skills]]
        if skills
        else ["skills: []"]
    )
    lines = [
        "---",
        f"persona_id: {persona_id}",
        f'version: "{version}"',
        *tool_lines,
        *skill_lines,
        "---",
        "",
        f"# {persona_id}",
        "",
        "## AstrBot 手动配置",
        "",
        "按文件头的 `tools` 和 `skills` 在 AstrBot WebUI 中手动绑定。",
        "不要把未列出的 Shell、Python、通用 HTTP 或通用文件写入能力作为替代路径绑定给该人格。",
        "",
        "## System Prompt",
        "",
        "复制下面代码块中的全部内容到 AstrBot Persona 的 System Prompt：",
        "",
        "```text",
        system_prompt,
        "```",
        "",
    ]
    if begin_dialogs:
        lines.extend(
            [
                "## Begin Dialogs",
                "",
                "如 AstrBot 配置中需要起始对话，按以下 JSON 手动填写：",
                "",
                "```json",
                json.dumps(begin_dialogs, ensure_ascii=False, indent=2),
                "```",
                "",
            ]
        )
    return "\n".join(lines)


def export_personas(root: Path, output: Path) -> list[Artifact]:
    personas = root / "personas"
    if not personas.is_dir():
        return []

    bindings = load_persona_bindings(personas)
    sources = sorted(personas.glob("persona_*_v*.json"))
    if not sources:
        raise ValueError(f"No Persona sources found in {personas}")

    items: list[Artifact] = []
    seen: set[str] = set()
    for source in sources:
        persona_id, version, system_prompt, begin_dialogs = load_persona_source(source)
        if persona_id in seen:
            raise ValueError(f"Duplicate Persona source for {persona_id}")
        seen.add(persona_id)
        binding = bindings.get(persona_id)
        if binding is None:
            raise ValueError(f"Missing manual bindings for Persona {persona_id}")

        target = output / "personas" / f"{persona_id}-{version}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            render_persona_markdown(
                persona_id=persona_id,
                version=version,
                system_prompt=system_prompt,
                begin_dialogs=begin_dialogs,
                tools=binding["tools"],
                skills=binding["skills"],
            ),
            encoding="utf-8",
        )
        items.append(
            artifact(root, "persona", persona_id, version, source, target)
        )

    extras = sorted(set(bindings) - seen)
    if extras:
        raise ValueError(
            "Persona bindings have no matching source: " + ", ".join(extras)
        )
    return items


def package_components(root: Path, output: Path) -> list[Artifact]:
    items: list[Artifact] = []
    for plugin in sorted(path for path in (root / "plugins").iterdir() if path.is_dir()):
        version = plugin_version(plugin)
        target = output / "plugins" / f"{plugin.name}-{version}.zip"
        write_zip(plugin, target)
        items.append(artifact(root, "plugin", plugin.name, version, plugin, target))

    versions = skill_versions(root)
    for skill in sorted(path for path in (root / "skills").iterdir() if path.is_dir()):
        if not (skill / "SKILL.md").is_file():
            raise ValueError(f"Invalid AstrBot Skill directory: {skill}")
        version = versions.get(skill.name)
        suffix = f"-{version}" if version else ""
        target = output / "skills" / f"{skill.name}{suffix}.zip"
        write_zip(skill, target)
        items.append(artifact(root, "skill", skill.name, version, skill, target))

    items.extend(export_personas(root, output))
    return items


def build_release(root: Path, output: Path, clean: bool) -> list[Artifact]:
    if clean and output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)
    items = package_components(root, output)
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project": "ContractBotConfig",
        "artifacts": [asdict(item) for item in items],
    }
    (output / "MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return items
