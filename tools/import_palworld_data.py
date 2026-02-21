#!/usr/bin/env python3
"""
Palworld Tech Tree Data Import Tool

Reads FModel JSON exports and produces a SQLite database for runtime use by
TechShuffleMod (via APClientLib's db_query API).

This tool is DATA IMPORT ONLY — it does NOT generate logic, manifests, or
item classifications. All game logic lives in the manifest.

Usage:
    python import_palworld_data.py <export_dir> [--output palworld_tech.db]

Where <export_dir> contains:
    Pal/Content/Pal/DataTable/Technology/DT_TechnologyRecipeUnlock.json

Output:
    - palworld_tech.db: SQLite database with tech data
    - Also generates vocabulary template files for manifest validation
"""

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path


def find_tech_json(export_dir: Path) -> Path:
    """Find DT_TechnologyRecipeUnlock.json in the export directory."""
    candidates = [
        export_dir / "Pal" / "Content" / "Pal" / "DataTable" / "Technology" / "DT_TechnologyRecipeUnlock.json",
        export_dir / "DT_TechnologyRecipeUnlock.json",
    ]
    for p in candidates:
        if p.exists():
            return p
    raise FileNotFoundError(
        f"DT_TechnologyRecipeUnlock.json not found in {export_dir}\n"
        "Expected at: Pal/Content/Pal/DataTable/Technology/DT_TechnologyRecipeUnlock.json"
    )


def parse_fmodel_json(filepath: Path) -> dict:
    """Parse FModel CompositeDataTable JSON export.

    The file is an array with a single object containing a 'Rows' dict.
    Each key in Rows is a tech ID, and the value is the tech's properties.
    """
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list) and len(data) > 0:
        data = data[0]

    if "Rows" not in data:
        raise ValueError("Expected 'Rows' key in JSON data")

    return data["Rows"]


def get_tier_from_level(level_cap: int) -> int:
    """Map LevelCap to tier (1-6)."""
    if level_cap <= 10:
        return 1
    elif level_cap <= 20:
        return 2
    elif level_cap <= 30:
        return 3
    elif level_cap <= 40:
        return 4
    elif level_cap <= 50:
        return 5
    else:
        return 6


def create_database(db_path: Path, rows: dict) -> None:
    """Create SQLite database from parsed tech data."""
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE techs (
            tech_id TEXT PRIMARY KEY,
            level_cap INTEGER NOT NULL,
            tier INTEGER NOT NULL,
            cost INTEGER NOT NULL,
            boss_requirement TEXT NOT NULL DEFAULT 'EPalBossType::None',
            parent_tech TEXT NOT NULL DEFAULT 'None',
            research_requirement TEXT NOT NULL DEFAULT 'None',
            is_boss_tech INTEGER NOT NULL DEFAULT 0,
            recipes_json TEXT NOT NULL DEFAULT '[]',
            builds_json TEXT NOT NULL DEFAULT '[]',
            name_key TEXT NOT NULL DEFAULT '',
            desc_key TEXT NOT NULL DEFAULT '',
            icon_name TEXT NOT NULL DEFAULT ''
        )
    """)

    for tech_id, props in rows.items():
        level_cap = props.get("LevelCap", 0)
        tier = get_tier_from_level(level_cap)

        cursor.execute("""
            INSERT INTO techs (
                tech_id, level_cap, tier, cost, boss_requirement,
                parent_tech, research_requirement, is_boss_tech,
                recipes_json, builds_json, name_key, desc_key, icon_name
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            tech_id,
            level_cap,
            tier,
            props.get("Cost", 1),
            props.get("RequireDefeatTowerBoss", "EPalBossType::None"),
            props.get("RequireTechnology", "None"),
            props.get("RequireResearchId", "None"),
            1 if props.get("IsBossTechnology", False) else 0,
            json.dumps(props.get("UnlockItemRecipes", [])),
            json.dumps(props.get("UnlockBuildObjects", [])),
            props.get("Name", ""),
            props.get("Description", ""),
            props.get("IconName", ""),
        ))

    conn.commit()
    conn.close()
    print(f"Created database: {db_path} ({len(rows)} techs)")


def generate_vocab_templates(rows: dict, output_dir: Path) -> None:
    """Generate vocabulary template JSON files for manifest validation."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Items vocabulary: "Tech Unlock: <display_name>" for each tech
    # We use tech_id as the display name since we don't have localization
    item_names = []
    location_names = []

    for tech_id in sorted(rows.keys()):
        item_names.append(f"Tech Unlock: {tech_id}")
        location_names.append(f"Tech: {tech_id}")

    # Add boss victory items
    bosses = ["Grass Boss", "Forest Boss", "Desert Boss",
              "Electric Boss", "Snow Boss", "Sakura Boss", "Viking Boss"]
    for boss in bosses:
        item_names.append(f"{boss} Victory")

    # Add tier keys
    for tier in range(2, 7):
        item_names.append(f"Tech Tier {tier} Key")

    # Add filler/trap
    item_names.append("Tech Points")
    item_names.append("Pal Raid Trap")

    # Regions vocabulary
    regions = [
        "Tech Tier 1", "Tech Tier 2", "Tech Tier 3",
        "Tech Tier 4", "Tech Tier 5", "Tech Tier 6",
        "Post-Grass Boss", "Post-Forest Boss", "Post-Desert Boss",
        "Post-Electric Boss", "Post-Snow Boss", "Post-Sakura Boss",
        "Post-Viking Boss"
    ]

    # Write vocab files
    items_path = output_dir / "Items.json"
    with open(items_path, "w", encoding="utf-8") as f:
        json.dump({"items": sorted(item_names)}, f, indent=2)
    print(f"Wrote items vocabulary: {items_path} ({len(item_names)} entries)")

    locations_path = output_dir / "Locations.json"
    with open(locations_path, "w", encoding="utf-8") as f:
        json.dump({"locations": sorted(location_names)}, f, indent=2)
    print(f"Wrote locations vocabulary: {locations_path} ({len(location_names)} entries)")

    regions_path = output_dir / "Regions.json"
    with open(regions_path, "w", encoding="utf-8") as f:
        json.dump({"regions": regions}, f, indent=2)
    print(f"Wrote regions vocabulary: {regions_path} ({len(regions)} entries)")


def print_stats(rows: dict) -> None:
    """Print summary statistics about the tech data."""
    total = len(rows)
    boss_gated = sum(1 for r in rows.values()
                     if r.get("RequireDefeatTowerBoss", "EPalBossType::None") != "EPalBossType::None")
    is_boss_tech = sum(1 for r in rows.values() if r.get("IsBossTechnology", False))
    has_parent = sum(1 for r in rows.values()
                     if r.get("RequireTechnology", "None") != "None")
    has_research = sum(1 for r in rows.values()
                       if r.get("RequireResearchId", "None") != "None")

    # Level distribution
    level_counts = {}
    for r in rows.values():
        lv = r.get("LevelCap", 0)
        level_counts[lv] = level_counts.get(lv, 0) + 1

    # Tier distribution
    tier_counts = {}
    for lv, count in level_counts.items():
        tier = get_tier_from_level(lv)
        tier_counts[tier] = tier_counts.get(tier, 0) + count

    print(f"\n--- Tech Data Summary ---")
    print(f"Total techs: {total}")
    print(f"Boss-gated: {boss_gated}")
    print(f"IsBossTechnology: {is_boss_tech}")
    print(f"Has parent tech: {has_parent}")
    print(f"Has research req: {has_research}")
    print(f"\nTier distribution:")
    for tier in sorted(tier_counts.keys()):
        print(f"  Tier {tier} (LevelCap {(tier-1)*10+1}-{tier*10 if tier < 6 else 65}): "
              f"{tier_counts[tier]} techs")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Import Palworld tech tree data from FModel exports into SQLite"
    )
    parser.add_argument("export_dir",
                        help="Path to FModel export directory (e.g., Exports/Palworld/0.7.1)")
    parser.add_argument("--output", "-o", default="palworld_tech.db",
                        help="Output database path (default: palworld_tech.db)")
    parser.add_argument("--vocab-dir", "-v", default=None,
                        help="Output directory for vocabulary templates "
                             "(default: Templates/Palworld relative to project root)")
    parser.add_argument("--stats", action="store_true",
                        help="Print tech data statistics")

    args = parser.parse_args()

    export_dir = Path(args.export_dir)
    if not export_dir.exists():
        print(f"Error: Export directory not found: {export_dir}", file=sys.stderr)
        sys.exit(1)

    # Find and parse the JSON
    json_path = find_tech_json(export_dir)
    print(f"Reading: {json_path}")
    rows = parse_fmodel_json(json_path)

    if args.stats:
        print_stats(rows)

    # Create database
    db_path = Path(args.output)
    create_database(db_path, rows)

    # Generate vocabulary templates
    if args.vocab_dir:
        vocab_dir = Path(args.vocab_dir)
    else:
        # Default: Templates/Palworld relative to this script's project
        project_root = Path(__file__).parent.parent
        vocab_dir = project_root / "Templates" / "Palworld"

    generate_vocab_templates(rows, vocab_dir)

    print("\nDone!")


if __name__ == "__main__":
    main()
