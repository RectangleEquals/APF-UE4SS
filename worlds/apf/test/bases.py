"""
APFramework test base classes and fixture helpers.

Fixtures are loaded from APF_TEST_FIXTURES_DIR env var (set by CI after gen_capabilities.py).
Falls back to worlds/apf/test/fixtures/ for local dev convenience (gitignored directory).

Fixture files contain the raw base64-encoded capabilities_data string (as output by
CapabilitiesBuilder.to_capabilities_data() / gen_capabilities.py).

Option variant files live alongside fixtures:
    <stem>.json               — base64 capabilities_data
    <stem>_<variant>.options.json — {"goal": "...", ...} extra options for that variant
"""

import json
import os
from pathlib import Path

from test.bases import WorldTestBase

# ---------------------------------------------------------------------------
# Fixture loading
# ---------------------------------------------------------------------------

_FIXTURES_DIR = Path(
    os.environ.get(
        "APF_TEST_FIXTURES_DIR",
        Path(__file__).parent / "fixtures",
    )
)


def list_fixtures() -> dict[str, str]:
    """
    Return {stem: base64_capabilities_data} for all .json fixture files in
    APF_TEST_FIXTURES_DIR that do NOT end in .options.json.
    """
    if not _FIXTURES_DIR.exists():
        return {}
    return {
        p.stem: p.read_text(encoding="ascii").strip()
        for p in sorted(_FIXTURES_DIR.glob("*.json"))
        if not p.stem.endswith(".options")
    }


def list_option_variants(stem: str) -> dict[str, dict]:
    """
    Return {variant_name: options_dict} for all <stem>_<variant>.options.json
    files found next to the fixture.
    """
    if not _FIXTURES_DIR.exists():
        return {}
    variants: dict[str, dict] = {}
    prefix = stem + "_"
    for p in sorted(_FIXTURES_DIR.glob(f"{stem}_*.options.json")):
        variant = p.stem[len(prefix):]  # strip "<stem>_" prefix + ".options" already gone
        try:
            variants[variant] = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return variants


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------

class APFrameworkTestBase(WorldTestBase):
    """
    Base for APFramework WorldTestBase tests.

    Subclasses provide capabilities_data in options (base64-encoded).
    auto_construct = True so AP's standard test machinery runs normally.
    """
    game = "APFramework"
