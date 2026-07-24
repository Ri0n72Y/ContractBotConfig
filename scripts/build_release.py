#!/usr/bin/env python3
"""Build installable ZIP packages for ContractBot AstrBot components."""

from __future__ import annotations

import argparse
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


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


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


def write_deterministic_zip(
    source: Path,
    output: Path,
    *,
    include_source_root: bool,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        output,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for path in included_files(source):
            relative = path.relative_to(source)
            archive_name = (
                Path(source.name) / relative
                if include_source_root
                else relative
            )
            info = zipfile.ZipInfo(str(archive_name).replace("\\", "/"))
            info.date_time = ZIP_TIMESTAMP
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())


def file_sha256(path: Path) -> str:
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
    versions_path = root / "VERSIONS.md"
    if not versions_path.is_file():
        return {}
    versions: dict[str, str] = {}
    in_skills = False
    for line in versions_path.read_text(encoding="utf-8").splitlines():
        if line.strip() == "## Skills":
            in_skills = True
            continue
        if in_skills and line.startswith("## "):
            break
        if not in_skills:
            continue
        match = re.match(r"-\s+([^:]+):\s*(\S+)", line.strip())
        if match:
            versions[match.group(1).strip()] = match.group(2).strip()
    return versions


def add_artifact(
    artifacts: list[Artifact],
    category: str,
    name: str,
    version: str | None,
    source: Path,
    output: Path,
    root: Path,
) -> None:
    artifacts.append(
        Artifact(
            category=category,
            name=name,
            version=version,
            source=str(source.relative_to(root)),
            file=str(output.relative_to(root)),
            size_bytes=output.stat().st_size,
            sha256=file_sha256(output),
        )
    )


def build(root: Path, output_root: Path, clean: bool) -> list[Artifact]:
    if clean and output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    artifacts: list[Artifact] = []

    plugins_root = root / "plugins"
    for plugin in sorted(path for path in plugins_root.iterdir() if path.is_dir()):
        version = plugin_version(plugin)
        output = output_root / "plugins" / f"{plugin.name}-{version}.zip"
        write_deterministic_zip(plugin, output, include_source_root=True)
        add_artifact(
            artifacts, "plugin", plugin.name, version, plugin, output, root
        )

    known_skill_versions = skill_versions(root)
    skills_root = root / "skills"
    for skill in sorted(path for path in skills_root.iterdir() if path.is_dir()):
        if not (skill / "SKILL.md").is_file():
            raise ValueError(f"Invalid AstrBot Skill directory: {skill}")
        version = known_skill_versions.get(skill.name)
        suffix = f"-{version}" if version else ""
        output = output_root / "skills" / f"{skill.name}{suffix}.zip"
        write_deterministic_zip(skill, output, include_source_root=True)
        add_artifact(
            artifacts, "skill", skill.name, version, skill, output, root
        )

    personas_root = root / "personas"
    if personas_root.is_dir():
        output = output_root / "personas" / "contract-personas.zip"
        write_deterministic_zip(
            personas_root,
            output,
            include_source_root=True,
        )
        add_artifact(
            artifacts,
            "personas",
            "contract-personas",
            None,
            personas_root,
            output,
            root,
        )

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project": "ContractBotConfig",
        "artifacts": [asdict(item) for item in artifacts],
    }
    (output_root / "MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return artifacts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Package ContractBot plugins, Skills and Personas."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output directory; defaults to <project>/dist.",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove the output directory before building.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = project_root()
    output_root = (args.output or (root / "dist")).resolve()
    artifacts = build(root, output_root, args.clean)
    print(f"Built {len(artifacts)} artifacts in {output_root}")
    for artifact in artifacts:
        version = f" {artifact.version}" if artifact.version else ""
        print(
            f"- {artifact.category}: {artifact.name}{version} "
            f"[{artifact.sha256[:12]}]"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
