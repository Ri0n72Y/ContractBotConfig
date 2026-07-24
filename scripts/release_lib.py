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
from typing import Iterable

EXCLUDED_NAMES = {".DS_Store", "__pycache__", ".git"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".log", ".tmp"}
ZIP_TIMESTAMP = (2026, 1, 1, 0, 0, 0)


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
        source=str(source.relative_to(root)),
        file=str(output.relative_to(root)),
        size_bytes=output.stat().st_size,
        sha256=sha256(output),
    )


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

    personas = root / "personas"
    if personas.is_dir():
        target = output / "personas" / "contract-personas.zip"
        write_zip(personas, target)
        items.append(artifact(root, "personas", "contract-personas", None, personas, target))
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
