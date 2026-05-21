"""
gen_capabilities.py — CLI wrapper for CapabilitiesBuilder.

All assembly logic lives in CapabilitiesBuilder. This script just parses
arguments and delegates to it. CI-friendly: exits non-zero on any error.

Usage:
    python tools/scripts/gen_capabilities.py <manifest.json> [<manifest2.json> ...]
            --output <dir>
            [--templates-dir <dir>]   # repeatable; searched for capabilities.include resolution
            [--game <name>]           # default: APFramework
            [--strict]                # treat missing deps as errors (default: warnings)
            [--raw]                   # also write <mod_id>_raw.json (human-readable)

Output:
    <output>/<mod_id>.json          — base64-encoded capabilities_data (for APF_TEST_FIXTURES_DIR)

Exit codes:
    0  — success
    1  — parse/validation/IO error
"""

import argparse
import json
import sys
from pathlib import Path

# Allow running from repo root or from tools/
_SCRIPT_DIR = Path(__file__).parent
_APF_MANAGER_DIR = _SCRIPT_DIR.parent / "apf_manager"
sys.path.insert(0, str(_APF_MANAGER_DIR.parent))  # makes "plugins.mods..." importable

from apf_manager.plugins.content.models.mods.capabilities import CapabilitiesBuilder  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="gen_capabilities.py",
        description="Assemble APF capabilities JSON from one or more mod manifests.",
    )
    parser.add_argument(
        "manifests",
        metavar="manifest.json",
        nargs="+",
        help="Path(s) to mod manifest.json file(s)",
    )
    parser.add_argument(
        "--output", "-o",
        required=True,
        metavar="DIR",
        help="Directory to write output files into",
    )
    parser.add_argument(
        "--templates-dir", "-t",
        action="append",
        dest="templates_dirs",
        default=[],
        metavar="DIR",
        help="Directory to search for capabilities.include fragments (repeatable)",
    )
    parser.add_argument(
        "--game",
        default="APFramework",
        help="Game name written into capabilities (default: APFramework)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help="Treat missing required dependencies as errors instead of warnings",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        default=False,
        help="Also write <mod_id>_raw.json with human-readable (non-base64) capabilities",
    )

    args = parser.parse_args(argv)

    manifest_paths = [Path(p) for p in args.manifests]
    templates_dirs = [Path(d) for d in args.templates_dirs]
    output_dir = Path(args.output)

    # Validate inputs
    for p in manifest_paths:
        if not p.exists():
            print(f"ERROR: manifest not found: {p}", file=sys.stderr)
            return 1
    for d in templates_dirs:
        if not d.is_dir():
            print(f"WARNING: templates-dir does not exist: {d}", file=sys.stderr)

    output_dir.mkdir(parents=True, exist_ok=True)

    builder = CapabilitiesBuilder()

    # Determine output filename stem from mod_id of first manifest
    def _stem_from_manifest(path: Path) -> str:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            mod_id = raw.get("mod_id", "")
            if mod_id:
                # Use the last component of the dot-separated mod_id
                return mod_id.split(".")[-1]
        except Exception:
            pass
        return path.stem

    stem = _stem_from_manifest(manifest_paths[0])

    try:
        caps = builder.from_manifest_path(
            *manifest_paths,
            game=args.game,
            templates_dirs=templates_dirs,
            strict=args.strict,
        )
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    # Write base64-encoded capabilities_data (used as fixture for APF_TEST_FIXTURES_DIR)
    caps_data = CapabilitiesBuilder.to_capabilities_data(caps)
    out_path = output_dir / f"{stem}.json"
    out_path.write_text(caps_data, encoding="ascii")
    print(f"Written: {out_path}")

    # Optionally write human-readable JSON
    if args.raw:
        raw_path = output_dir / f"{stem}_raw.json"
        raw_path.write_text(json.dumps(caps, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Written: {raw_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
