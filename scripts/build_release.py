#!/usr/bin/env python3
"""Build ContractBot release artifacts."""

from __future__ import annotations

import argparse
from pathlib import Path

from release_lib import build_release


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Package ContractBot plugins and Skills, and export Personas."
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
    output = (args.output or (root / "dist")).resolve()
    artifacts = build_release(root, output, args.clean)
    print(f"Built {len(artifacts)} artifacts in {output}")
    for item in artifacts:
        version = f" {item.version}" if item.version else ""
        print(
            f"- {item.category}: {item.name}{version} "
            f"[{item.sha256[:12]}]"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
