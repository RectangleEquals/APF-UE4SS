#!/usr/bin/env python3
"""
TechShuffle Manifest Generator

Generates the full manifest.json for PalworldTechShuffle from the SQLite
database created by import_palworld_data.py.

The generated manifest IS the source of truth — all logic lives in it.
This tool is a one-time generator; the output can be manually edited afterward.

Usage:
    python generate_manifest.py palworld_tech.db --output manifest.json
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path


# =============================================================================
# Boss type to name mapping
# =============================================================================
BOSS_MAP = {
    "EPalBossType::GrassBoss": "Grass Boss",
    "EPalBossType::ForestBoss": "Forest Boss",
    "EPalBossType::DesertBoss": "Desert Boss",
    "EPalBossType::ElectricBoss": "Electric Boss",
    "EPalBossType::SnowBoss": "Snow Boss",
    "EPalBossType::SakurajimaBoss": "Sakura Boss",
    "EPalBossType::VikingBoss": "Viking Boss",
}

# =============================================================================
# Item classification — all tech_ids must match DT_TechnologyRecipeUnlock rows
# =============================================================================
# CRITICAL items for core gameplay progression (~53 techs, always in pool)
KEY_TECHS = {
    # === Tier 1 (Lv 1-10) Core Survival ===
    "Workbench",                                   # Primitive Workbench — all crafting
    "PALBOX",                                      # Pal Box — base building
    "GlobalPalStorage",                            # Global Pal Storage
    "Product_Axe_Grade_01",                        # Stone Axe
    "Product_Pickaxe_Grade_01",                    # Stone Pickaxe
    "HandTorch",                                   # Hand Torch
    "SkinChange",                                  # Pal Dressing Facility
    "Infra_ItemChest_Grade_01",                    # Wooden Chest
    "Product_Cooking_Grade_01",                    # Campfire / Cooking Pot
    "RepairBench",                                 # Repair Bench
    "Special_PalSphere_Grade_01",                  # Pal Sphere — catch pals
    "Arrow",                                       # Arrow
    "Battle_RangeWeapon_Bow1",                     # Old Bow
    "Battle_Cloth",                                # Cloth (crafting material)
    "Infra_PalBed_Grade_01",                       # Pal Bed
    "Infra_PlayerBed_Grade_01",                    # Player Bed
    "RepairKit",                                   # Repair Kit
    "Battle_Armor_Grade_01_Cloth",                 # Cloth Outfit
    "PalFoodBox",                                  # Feed Box
    "Shield_01",                                   # Common Shield
    "BaseCampBattleDirector",                      # Alarm Bell — base defense
    "Spear",                                       # Spear
    "Battle_Glider_Grade_01",                      # Normal Parachute
    "MonsterFarm",                                 # Ranch
    "Product_Farm_Berries",                        # Berry Plantation
    "BuildableGoddessStatue",                      # Statue of Power
    "Product_WorkBench_SkillUnlock",               # Pal Gear Workbench
    "SkillUnlock_Boar",                            # Rushboar Saddle (first mount)
    "SkillUnlock_FlyingManta",                     # Celaray Gloves (first flying)
    "SkillUnlock_Alpaca",                          # Melpaca Saddle
    "Special_HatchingPalEgg",                      # Egg Incubator
    "Product_StationDeforest",                     # Logging Site
    "Product_StonePit",                            # Stone Pit
    "Crusher",                                     # Crusher
    "Battle_RangeWeapon_Bow3",                     # Three Shot Bow
    "Infra_MachineParts",                          # Nails / Parts production
    "Product_Ingot_Grade_01_Copper",               # Copper Smelter
    "AutoMealPouch_Tier1",                         # Basic Meal Pouch

    # === Tier 2 (Lv 11-20) Early-Mid Progression ===
    "Product_Axe_Grade_02",                        # Metal Axe
    "Product_Pickaxe_Grade_02",                    # Metal Pickaxe
    "Product_Factory_Hard_Grade_01",               # High Quality Workbench
    "GrapplingGun",                                # Grappling Gun
    "Battle_RangeWeapon_BowGun",                   # Crossbow
    "Special_PalSphere_Grade_02",                  # Mega Sphere
    "Special_SphereFactory_Black_Grade_01",        # Sphere Workbench
    "Battle_Glider_Grade_02",                      # Mega Glider
    "Special_PalSphere_Grade_03",                  # Giga Sphere
    "Product_WeaponFactory_Dirty_Grade_01",        # Weapon Workbench
    "BreedFarm",                                   # Breeding Farm

    # === Tier 3+ Essential Gates ===
    "Infra_ElectricGenerator_Grade_01",            # Electric Generator
    "Battle_RangeWeapon_HandGun",                  # Handgun
    "HandgunBullet",                               # Handgun Ammo
    "Product_Ingot_Grade_02_Iron",                 # Iron Smelter
}

# Additional important gameplay techs for standard scope (~152 extra techs)
STANDARD_EXTRA_TECHS = {
    # === Tier 1 extras ===
    "Battle_MeleeWeapon_Bat",                      # Wooden Club
    "Wooden_houseset",                             # Wooden Housing
    "Arrow_Fire",                                  # Fire Arrow
    "Battle_RangeWeapon_Bow_Fire",                 # Fire Bow
    "Torch",                                       # Standing Torch
    "SkillUnlock_Kitsunebi",                       # Foxparks Harness
    "Battle_MeleeWeapon_Bat2",                     # Bat Mk2
    "Arrow_Poison",                                # Poison Arrow
    "Battle_RangeWeapon_Bow_Poison",               # Poison Bow
    "SkillUnlock_DreamDemon",                      # Daydream Necklace
    "SkillUnlock_Hedgehog",                        # Jolthog Saddle
    "Battle_Armor_Grade_01_Cloth_Cold",            # Cloth Outfit (Cold)
    "Battle_Armor_Grade_01_Cloth_Heat",            # Cloth Outfit (Heat)
    "Spa",                                         # Hot Spring
    "DefenseWait",                                 # Patrol Command
    "SkillUnlock_Garm",                            # Direhowl Saddle
    "SkillUnlock_NegativeOctopus",                 # Depresso Saddle
    "SkillUnlock_Serpent",                         # Surfent Saddle
    "Trap_LegHold",                                # Leg Hold Trap
    "Battle_Helm_Grade_02_Fur",                    # Fur Helmet
    "Trap_Noose",                                  # Noose Trap

    # === Tier 2 extras ===
    "SphereModule_Heavy",                          # Heavy Sphere Module
    "Battle_Armor_Grade_02_Fur",                   # Pelt Armor
    "MeatCutterKnife",                             # Meat Cleaver
    "Product_Medicine_Grade_01",                   # Medicine
    "SkillUnlock_Deer",                            # Eikthyrdeer Saddle
    "SkillUnlock_Monkey",                          # Tanzee Saddle
    "SkillUnlock_NaughtyCat",                      # Galeclaw Gloves
    "Battle_RangeWeapon_BowGun_Fire",              # Fire Crossbow
    "ManualElectricGenerator",                     # Manual Generator
    "SkillUnlock_WeaselDragon",                    # Vanwyrm Saddle
    "Spear_2",                                     # Metal Spear
    "SkillUnlock_Kirin",                           # Univolt Saddle
    "Special_PalRankUp",                           # Pal Essence Condenser
    "Lantern",                                     # Lantern (boss-gated)
    "Product_Farm_wheat",                          # Wheat Plantation
    "SkillUnlock_HawkBird",                        # Nitewing Saddle
    "Battle_Armor_Grade_02_Fur_Heat",              # Pelt Armor (Heat)
    "Infra_ItemChest_Grade_02",                    # Large Chest
    "Shield_02",                                   # Mega Shield
    "SkillUnlock_FlameBuffalo",                    # Arsox Saddle
    "Unlock_Picking_Tier1",                        # Picking I
    "Battle_RangeWeapon_BowGun_Poison",            # Poison Crossbow
    "GrapplingGun2",                               # Grappling Gun Mk2
    "Heater",                                      # Heater
    "Product_Cooking_Grade_02",                    # Cooking Pot II
    "SkillUnlock_Penguin",                         # Pengullet Saddle
    "Battle_Armor_Grade_02_Fur_Cold",              # Pelt Armor (Cold)
    "Cooler",                                      # Cooler
    "Stone_houseset",                              # Stone Housing
    "AutoMealPouch_Tier2",                         # Meal Pouch II
    "Cement",                                      # Cement
    "DimensionPalStorage",                         # Dimension Pal Storage
    "Lab",                                         # Pal Essences Lab
    "ToolBoxV1",                                   # Tool Box

    # === Tier 3 extras ===
    "Musket",                                      # Musket
    "RoughBullet",                                 # Coarse Ammo
    "ElecBaton",                                   # Electric Baton
    "Battle_Armor_Grade_03_Copper",                # Copper Armor
    "Battle_Helm_Grade_03_Copper",                 # Copper Helmet
    "SphereModule_Curve",                          # Curve Sphere Module
    "MakeshiftHandgun",                            # Makeshift Handgun
    "Product_CopperPit",                           # Copper Pit (boss-gated)
    "FragGrenade",                                 # Frag Grenade
    "Silo",                                        # Silo
    "Unlock_Picking_Tier2",                        # Picking II
    "Battle_RangeWeapon_SphereLauncher_Once",      # Single-shot Sphere Launcher
    "MakeshiftSubmachineGun",                      # Makeshift SMG
    "AdditionalInventory_001",                     # Inventory +1
    "Special_PalSphere_Grade_04",                  # Hyper Sphere
    "Special_SphereFactory_Black_Grade_02",        # Sphere Workbench II
    "Shield_03",                                   # Giga Shield
    "Product_Factory_Hard_Grade_02",               # Production Assembly Line
    "Battle_Armor_Grade_03_Copper_Heat",           # Copper Armor (Heat)
    "Battle_Armor_Grade_03_Copper_Cold",           # Copper Armor (Cold)
    "Lantern_High",                                # High Lantern
    "Infra_PlayerBed_Grade_02",                    # Player Bed II
    "DefenseWall",                                 # Stone Wall
    "Battle_MeleeWeapon_Sword",                    # Metal Sword
    "MakeshiftShotgun",                            # Makeshift Shotgun
    "Metal_houseset",                              # Metal Housing
    "MiningTool",                                  # Mining Tool

    # === Tier 4 extras ===
    "GrapplingGun3",                               # Grappling Gun Mk3
    "MakeshiftAssaultRifle",                       # Makeshift Assault Rifle
    "SphereModule_Sniper",                         # Sniper Module
    "Battle_RangeWeapon_CompoundBow",              # Compound Bow
    "Product_WeaponFactory_Dirty_Grade_02",        # Weapon Assembly Line
    "ReinforcedArrow",                             # Reinforced Arrow
    "Product_Axe_Grade_03",                        # Mega Axe
    "Product_Pickaxe_Grade_03",                    # Mega Pickaxe
    "Infra_ElectronicCircuit",                     # Electronic Circuit
    "CarbonFiber",                                 # Carbon Fiber
    "Special_PalSphere_Grade_05",                  # Ultra Sphere
    "Special_SphereFactory_Black_Grade_03",        # Sphere Assembly Line
    "AutoMealPouch_Tier3",                         # Meal Pouch III
    "AutoMealPouch_Tier4",                         # Meal Pouch IV
    "Battle_Armor_Grade_03_Iron",                  # Iron Armor
    "Battle_Helm_Grade_04_Iron",                   # Iron Helmet
    "Battle_RangeWeapon_SubmachineGun",            # SMG
    "Special_ElectricHatchingPalEgg",              # Electric Incubator
    "Battle_RangeWeapon_SphereLauncher",           # Sphere Launcher
    "Battle_RangeWeapon_ShotGun",                  # Shotgun
    "ShotGunBullet",                               # Shotgun Ammo
    "Battle_Glider_Grade_03",                      # Giga Glider
    "Infra_ItemChest_Grade_03",                    # Large Chest II
    "Accessory_AirDash1",                          # Air Dash I
    "Accessory_JumpCount_Increase1",               # Double Jump I
    "Battle_Armor_Grade_03_Iron_Heat",             # Iron Armor (Heat)
    "Battle_Armor_Grade_03_Iron_Cold",             # Iron Armor (Cold)

    # === Tier 5 extras ===
    "Battle_RangeWeapon_AssaultRifle",             # Assault Rifle
    "AssaultRifleBullet",                          # Assault Rifle Ammo
    "Battle_Armor_Grade_04_Steal",                 # Steel Armor
    "Battle_Helm_Grade_05_Steal",                  # Steel Helmet
    "Product_CoalPit",                             # Coal Pit (boss-gated)
    "Product_SulfurPit",                           # Sulfur Pit (boss-gated)
    "Shield_04",                                   # Shield IV
    "Product_Ingot_Grade_03_Steal",                # Steel Smelter
    "Katana",                                      # Katana
    "Special_PalSphere_Grade_06",                  # Legend Sphere
    "AdditionalInventory_002",                     # Inventory +2
    "Product_Factory_Hard_Grade_03",               # Assembly Line II
    "Product_WeaponFactory_Dirty_Grade_03",        # Weapon Assembly Line II
    "AutoMealPouch_Tier5",                         # Meal Pouch V
    "GrapplingGun4",                               # Grappling Gun Mk4
    "Battle_RangeWeapon_RocketLauncher",           # Rocket Launcher
    "LauncherBullet",                              # Rocket Ammo
    "ElectricGenerator_Large",                     # Large Generator
    "Plastic",                                     # Plastic
    "OilPump",                                     # Oil Pump
    "Battle_Armor_Grade_04_Steal_Heat",            # Steel Armor (Heat)
    "Battle_Armor_Grade_04_Steal_Cold",            # Steel Armor (Cold)

    # === Tier 6 extras ===
    "Battle_Armor_Grade_05_Plastic",               # Plastic Armor
    "Battle_Helm_Grade_06_Plastic",                # Plastic Helmet
    "Battle_RangeWeapon_LaserRifle",               # Laser Rifle
    "LaserBullet",                                 # Laser Ammo
    "Special_PalSphere_Grade_07",                  # Exotic Sphere
    "Product_QuartzPit",                           # Quartz Pit (boss-gated)
    "CrystalPit",                                  # Crystal Pit (boss-gated)
    "Battle_Glider_Grade_04",                      # Hyper Glider
    "GrapplingGun5",                               # Grappling Gun Mk5
    "Shield_05",                                   # Shield V
    "Unlock_Picking_Tier3",                        # Picking III
    "AdditionalInventory_003",                     # Inventory +3
    "AdditionalInventory_004",                     # Inventory +4
    "Accessory_AirDash2",                          # Air Dash II (boss-gated)
    "Accessory_AirDash3",                          # Air Dash III
    "Accessory_JumpCount_Increase2",               # Double Jump II (boss-gated)
    "SphereFactory_Black_04",                      # Sphere Assembly Line II
    "WeaponFactory_Dirty_04",                      # Weapon Assembly Line III
    "Factory_Hard_04",                             # Advanced Workshop
    "StainlessSteel",                              # Stainless Steel
    "ManganeseIngot",                              # Manganese Ingot
}


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


def get_scope(tech_id: str) -> str:
    """Determine scope classification: key, standard, or full."""
    if tech_id in KEY_TECHS:
        return "key"
    elif tech_id in STANDARD_EXTRA_TECHS:
        return "standard"
    else:
        return "full"


def get_item_type(tech_id: str, is_boss_tech: bool) -> str:
    """Determine AP item type based on classification."""
    if tech_id in KEY_TECHS:
        return "progression"
    elif tech_id in STANDARD_EXTRA_TECHS:
        return "useful"
    elif is_boss_tech:
        return "useful"
    else:
        return "useful"


def build_scope_logic(scope: str) -> str:
    """Build logic expression for scope filtering."""
    if scope == "key":
        return ""  # Always included
    elif scope == "standard":
        return "(Option: shuffle_scope == standard) OR (Option: shuffle_scope == full)"
    else:
        return "(Option: shuffle_scope == full)"


def build_boss_logic(boss_type: str) -> str:
    """Build logic expression for boss-gated techs."""
    boss_name = BOSS_MAP.get(boss_type)
    if not boss_name:
        return ""

    # When shuffle_boss_tech is on, require boss victory; when off, no boss requirement
    return (f"(Option: shuffle_boss_tech) AND (Item: {boss_name} Victory) "
            f"OR (Option: shuffle_boss_tech == false)")


def build_chain_logic(parent_tech: str) -> str:
    """Build logic expression for tech chain requirements."""
    if parent_tech == "None" or not parent_tech:
        return ""
    return f"(Item: Tech Unlock: {parent_tech})"


def combine_logic(*parts: str) -> str:
    """Combine multiple logic parts with AND."""
    non_empty = [p for p in parts if p]
    if not non_empty:
        return ""
    if len(non_empty) == 1:
        return non_empty[0]
    # Wrap each in parens to be safe
    wrapped = [f"({p})" if " OR " in p else p for p in non_empty]
    return " AND ".join(wrapped)


def generate_manifest(db_path: Path) -> dict:
    """Generate the full TechShuffle manifest from the database."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    techs = cursor.execute("""
        SELECT * FROM techs ORDER BY level_cap, tech_id
    """).fetchall()

    conn.close()

    # Build items array
    items = []

    # Boss Victory Items
    for boss_type, boss_name in sorted(BOSS_MAP.items(), key=lambda x: x[1]):
        items.append({
            "name": f"{boss_name} Victory",
            "type": "progression",
            "amount": 1,
            "action": "TechShuffle.OnBossVictory",
            "args": [{"name": "boss", "type": "string", "value": boss_type}]
        })

    # Tech Tier Keys
    for tier in range(2, 7):
        items.append({
            "name": f"Tech Tier {tier} Key",
            "type": "progression",
            "amount": 1,
            "action": "TechShuffle.UnlockTier",
            "args": [{"name": "tier", "type": "number", "value": tier}]
        })

    # Tech Unlock items (one per tech)
    # Scope filtering uses option-only logic:
    #   key items: no filter (always included)
    #   standard items: logic="(Option: shuffle_scope == standard) OR (Option: shuffle_scope == full)"
    #   full items: logic="(Option: shuffle_scope == full)"
    for tech in techs:
        tech_id = tech["tech_id"]
        scope = get_scope(tech_id)
        item_type = get_item_type(tech_id, bool(tech["is_boss_tech"]))

        item_entry = {
            "name": f"Tech Unlock: {tech_id}",
            "type": item_type,
            "amount": 1,
            "action": "TechShuffle.UnlockTech",
            "args": [{"name": "tech_id", "type": "string", "value": tech_id}]
        }

        # Add scope filter via logic field
        if scope == "standard":
            item_entry["logic"] = "(Option: shuffle_scope == standard) OR (Option: shuffle_scope == full)"
        elif scope == "full":
            item_entry["logic"] = "(Option: shuffle_scope == full)"
        # key scope: no filter needed

        items.append(item_entry)

    # Filler & Traps
    items.append({
        "name": "Tech Points",
        "type": "filler",
        "amount": -1,
        "action": "TechShuffle.GrantTechPoints",
        "args": [{"name": "amount", "type": "number", "value": 3}]
    })
    items.append({
        "name": "Pal Raid Trap",
        "type": "trap",
        "amount": -1,
        "action": "TechShuffle.TriggerRaid",
        "args": []
    })

    # Build locations array
    locations = []
    for tech in techs:
        tech_id = tech["tech_id"]
        tier = get_tier_from_level(tech["level_cap"])
        scope = get_scope(tech_id)

        # Build logic components
        scope_logic = build_scope_logic(scope)
        boss_logic = build_boss_logic(tech["boss_requirement"])
        chain_logic = build_chain_logic(tech["parent_tech"])
        full_logic = combine_logic(scope_logic, boss_logic, chain_logic)

        region_logic = f"(Can Access: Tech Tier {tier})"
        combined_logic = f"{region_logic} AND ({full_logic})" if full_logic else region_logic
        loc_entry = {
            "name": f"Tech: {tech_id}",
            "logic": combined_logic
        }

        locations.append(loc_entry)

    # Build the complete manifest
    manifest = {
        "mod_id": "spectrecular.palworld.techshuffle",
        "name": "Palworld Tech Shuffle",
        "version": "1.0.0",
        "enabled": True,
        "vocab_validation": True,
        "options": {
            "shuffle_scope": {
                "type": "text_choice",
                "choices": ["key", "standard", "full"],
                "default": "standard",
                "description": "Which techs to include: key (~53 essential), standard (~205 gameplay), full (all 502)"
            },
            "shuffle_boss_tech": {
                "type": "toggle",
                "default": True,
                "description": "Include boss-gated technologies in the shuffle"
            },
            "tier_progression": {
                "type": "text_choice",
                "choices": ["open", "keyed", "strict"],
                "default": "keyed",
                "description": "open=all tiers accessible, keyed=tier keys required, strict=sequential tiers"
            },
            "difficulty": {
                "type": "text_choice",
                "choices": ["easy", "normal", "hard"],
                "default": "normal",
                "description": "Logic difficulty — affects item progression classification"
            },
            "tech_visibility": {
                "type": "text_choice",
                "choices": ["locked", "hidden"],
                "default": "locked",
                "description": "locked=techs visible but unpurchasable, hidden=techs invisible until unlocked"
            },
            "tech_completion_pct": {
                "type": "range",
                "range_start": 25,
                "range_end": 100,
                "default": "75",
                "description": "Percentage of shuffled techs required (for tech_completion goal)"
            }
        },
        "goals": [
            {
                "name": "all_bosses",
                "display": "Defeat All Tower Bosses",
                "description": "Defeat all 7 tower bosses to win",
                "logic": "(Item: Grass Boss Victory) AND (Item: Forest Boss Victory) AND (Item: Desert Boss Victory) AND (Item: Electric Boss Victory) AND (Item: Snow Boss Victory) AND (Item: Sakura Boss Victory) AND (Item: Viking Boss Victory)"
            },
            {
                "name": "tech_completion",
                "display": "Tech Completion",
                "description": "Research the required percentage of shuffled techs",
                "logic": "True"
            }
        ],
        "capabilities": {
            "include": ["techshuffle/regions.json"],
            "items": items,
            "locations": locations
        }
    }

    return manifest


def main():
    parser = argparse.ArgumentParser(
        description="Generate TechShuffle manifest.json from SQLite database"
    )
    parser.add_argument("db_path",
                        help="Path to palworld_tech.db")
    parser.add_argument("--output", "-o", default="manifest.json",
                        help="Output manifest path (default: manifest.json)")

    args = parser.parse_args()

    db_path = Path(args.db_path)
    if not db_path.exists():
        print(f"Error: Database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    manifest = generate_manifest(db_path)

    output_path = Path(args.output)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=4, ensure_ascii=False)

    # Print stats
    items = manifest["capabilities"]["items"]
    locations = manifest["capabilities"]["locations"]

    boss_items = [i for i in items if "Victory" in i["name"]]
    tier_keys = [i for i in items if "Tier" in i["name"] and "Key" in i["name"]]
    tech_items = [i for i in items if i["name"].startswith("Tech Unlock:")]
    filler_items = [i for i in items if i["type"] == "filler"]
    trap_items = [i for i in items if i["type"] == "trap"]

    locs_with_logic = [l for l in locations if "logic" in l]
    locs_with_scope = [l for l in locations if "logic" in l and "shuffle_scope" in l.get("logic", "")]
    locs_with_boss = [l for l in locations if "logic" in l and "Boss Victory" in l.get("logic", "")]
    locs_with_chain = [l for l in locations if "logic" in l and "Tech Unlock:" in l.get("logic", "")]

    print(f"Generated manifest: {output_path}")
    print(f"  Items: {len(items)} total")
    print(f"    Boss Victories: {len(boss_items)}")
    print(f"    Tier Keys: {len(tier_keys)}")
    print(f"    Tech Unlocks: {len(tech_items)}")
    print(f"    Filler: {len(filler_items)}, Trap: {len(trap_items)}")
    print(f"  Locations: {len(locations)} total")
    print(f"    With logic: {len(locs_with_logic)}")
    print(f"    Scope-filtered: {len(locs_with_scope)}")
    print(f"    Boss-gated: {len(locs_with_boss)}")
    print(f"    Chain-locked: {len(locs_with_chain)}")

    # Count by scope
    prog = sum(1 for i in tech_items if i["type"] == "progression")
    useful = sum(1 for i in tech_items if i["type"] == "useful")
    print(f"  Item types: {prog} progression, {useful} useful")


if __name__ == "__main__":
    main()
