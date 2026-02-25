"""
APF Manager — entry point.

Usage (GUI):
    python tools/apf_manager
    python -m apf_manager          (from tools/)

Usage (CLI — headless, suitable for CI):
    python tools/apf_manager --cli [--deploy] [--validate] [--package] [--version TAG]
"""

from __future__ import annotations

import argparse
import sys

# Bootstrap: when run as `python apf_manager` (not `python -m apf_manager`),
# __package__ is None and relative imports fail. Fix by inserting tools/ into
# sys.path and setting __package__ so relative imports resolve correctly.
if __package__ is None or __package__ == "":
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    __package__ = "apf_manager"


def _run_gui() -> None:
    from .gui.app import APFManagerApp
    APFManagerApp().run()


def _run_cli(args: argparse.Namespace) -> int:
    """Headless CLI mode. Returns exit code."""
    from .config import APFConfig, APFState
    from .ue4ss import UE4SSDetector
    from .discovery import ModDiscovery
    from .engine import InstallEngine
    from .validator import Validator

    def log(msg: str) -> None:
        print(msg, flush=True)

    config = APFConfig.load().resolve()
    state = APFState.load()

    # UE4SS detection
    detector = UE4SSDetector()
    detection = detector.detect(config.game_root)
    if not detection.valid:
        log(f"[ERROR] UE4SS detection failed: {', '.join(detection.missing)}")
        return 1

    discovery = ModDiscovery(config)
    engine = InstallEngine(config, log=log)
    validator = Validator(config, discovery, state, detection, log=log)

    exit_code = 0

    if args.deploy:
        mods = discovery.discover()
        deployed = engine.deploy_all(mods, state, detection)
        if not deployed:
            exit_code = 1

    if args.validate:
        results = validator.validate_all()
        for status, label, detail in results:
            log(f"  [{status}] {label}: {detail}")
        if any(s == "ERROR" for s, _, _ in results):
            exit_code = 1

    if args.package:
        from .packager import PackageBuilder
        version = args.version or "dev"
        builder = PackageBuilder(config, discovery, log=log)
        out = builder.build(version)
        log(f"Package: {out}")

    state.save()
    return exit_code


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="apf_manager",
        description="AP Framework Manager — deploy, validate, and package AP mods.",
    )
    parser.add_argument("--cli", action="store_true", help="Run headless (no GUI)")
    parser.add_argument("--deploy", action="store_true", help="Deploy all mods (CLI mode)")
    parser.add_argument("--validate", action="store_true", help="Run validation checks (CLI mode)")
    parser.add_argument("--package", action="store_true", help="Build release zip (CLI mode)")
    parser.add_argument("--version", default="", help="Version tag for package (e.g. v0.1.0)")
    args = parser.parse_args()

    if args.cli:
        sys.exit(_run_cli(args))
    else:
        _run_gui()


if __name__ == "__main__":
    main()
