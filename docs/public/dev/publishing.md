# Publishing a Registry

This guide explains how to create and publish a GitHub-hosted mod registry that APF Manager can discover and install from.

---

## 1. Overview

A **registry** is a GitHub repository that APF Manager can traverse to find AP Framework mods and templates. Players add registry URLs in APF Manager → Mods → Registries tab. The app fetches everything over the GitHub API — no `git` required on the player's machine.

One registry can contain:
- One or more AP mods (each in their own subfolder)
- Template vocabularies under `Templates/<GameName>/`
- Links to other registries via Git submodules
- UE4SS install information (`ue4ss.json`) alongside a framework mod

---

## 2. Naming Conventions

### mod_id

Every AP Framework mod is identified by a `mod_id` in `manifest.json`. The format is:

```
author.game.modname
```

- `author` — your handle or organisation (e.g. `archipelago`, `mygame_team`)
- `game` — lowercase game identifier with no spaces (e.g. `palworld`, `satisfactory`)
- `modname` — the specific mod's name (e.g. `framework`, `techshuffle`, `tracker`)

**Framework mod convention:** The core framework mod for a game must have `mod_id = "archipelago.<game>.framework"` (exact format). APF Manager uses this pattern to identify the framework mod candidate.

### Folder naming

While folder names are arbitrary, `APFrameworkMod` is the strongly encouraged convention for the framework mod folder. This makes it easier for players to recognise the mod and for tooling to provide meaningful hints. Other mods should use descriptive names matching their purpose.

---

## 3. Mod Repository Structure

A mod repository contains one subfolder per mod, each with a `manifest.json`:

```
MyRegistry/
├── APFrameworkMod/
│   ├── manifest.json        ← mod_id: "archipelago.mygame.framework"
│   ├── ue4ss.json           ← optional UE4SS install options (framework only)
│   └── README.md            ← mod-level docs (shown in Mods tab preview)
├── MyItemShuffle/
│   ├── manifest.json        ← mod_id: "archipelago.mygame.itemshuffle"
│   └── README.md
└── README.md                ← repo-level docs (shown in Registries tab)
```

Rules:
- Each subfolder at **depth 1** that contains `manifest.json` is treated as a mod.
- `manifest.json` must contain at least `mod_id` to be recognised as an AP mod.
- Subfolders without `manifest.json` are ignored (except `Templates/` — see below).
- Nested mod directories (depth > 1) are not discovered.

### Documentation conventions

| File | Shown in UI |
|---|---|
| `<ModFolder>/README.md` | Mod preview pane in Mods tab; "Docs" button on mod row |
| Any `.md` adjacent to `manifest.json` | Same as above |
| Repo root `README.md` | Registry card → "View Docs" button in Registries tab |
| `docs/*.md` at repo root | Registry card → "View Docs" expands to file list |
| Any file with `ue4ss` in the name (case-insensitive) | UE4SS setup card → "Installation Guide" |

**Relative link resolution:** The app resolves non-absolute links in `.md` files against `raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}`. Links to `.md` files within the same repo render inline with back-navigation. All other links open the system browser.

---

## 4. Registry Repository Structure

A registry is any repo that resolves to at least one valid AP mod or template set. No descriptor file at the root is required.

```
MyRegistry/
├── APFrameworkMod/           ← mod subfolder (see Section 3)
│   ├── manifest.json
│   └── ue4ss.json
├── AnotherMod/
│   └── manifest.json
├── Templates/
│   └── Palworld/
│       ├── items.json        ← item vocabulary
│       ├── locations.json    ← location vocabulary
│       └── regions.json      ← region vocabulary (optional)
├── .gitmodules               ← optional: submodules to follow
└── README.md
```

**Container-only registries** (no mods, only templates or submodules) are valid. APF Manager will accept them as long as they contribute at least one template path.

**Submodule traversal:** Any Git submodule at the repo root is followed recursively (up to depth 3). This lets you split a large registry into focused sub-repos. Cycle detection prevents infinite loops.

---

## 5. `ue4ss.json` Reference

`ue4ss.json` sits in the same folder as the framework mod (`mod_id = "archipelago.<game>.framework"`). It describes how to obtain the correct UE4SS build for this game.

```json
{
  "options": [
    {
      "type": "github_release",
      "repo": "Okaetsu/RE-UE4SS",
      "tag": "experimental-palworld",
      "note": "Recommended for Palworld"
    },
    {
      "type": "external_url",
      "url": "https://www.nexusmods.com/palworld/mods/123",
      "note": "NexusMods alternative"
    },
    {
      "type": "manual",
      "note": "Follow the installation guide below"
    }
  ],
  "docs": "docs/ue4ss_setup.md",
  "note": "Required: Palworld needs a specific RE-UE4SS fork"
}
```

| Field | Description |
|---|---|
| `options` | Ordered list of install options; first is shown as primary |
| `options[].type` | `"github_release"` (auto-download), `"external_url"` (open browser), `"manual"` (show docs only) |
| `options[].repo` | For `github_release`: `"owner/repo"` — latest release is used unless `tag` is set |
| `options[].tag` | For `github_release`: specific release tag (e.g. `"experimental-palworld"`) |
| `options[].url` | For `external_url`: the URL to open |
| `options[].note` | Short explanation shown to the player |
| `docs` | Path to a `.md` file in this repo (relative to repo root) shown as "Installation Guide" |
| `note` | One-line notice shown in the UE4SS setup card |

**Alternatively**, a submodule in the framework mod's repo that points to a UE4SS repo (no `manifest.json` in that submodule) is automatically treated as a `github_release` entry for that repo's latest release.

---

## 6. Making Your Registry Discoverable

Tag your registry repo on GitHub with the appropriate topics to enable auto-discovery via APF Manager's "Search GitHub" button.

| Topic | Purpose |
|---|---|
| `apf-ue4ss-registry` | Universal marker — all APF registries should have this |
| `apf-ue4ss-registry-<game>` | Game-specific (e.g. `apf-ue4ss-registry-palworld`) — required for game-filtered search |
| `apf-ue4ss-registry-<game>-core` | Signals the repo contains a framework mod candidate — enables targeted UE4SS discovery |

**Add topics** in your repo: Settings → Topics → type and save. All three topics are recommended for any registry that contains a framework mod.

---

## 7. Documentation in the App

How `.md` files in your registry map to UI features:

| Location | UI feature |
|---|---|
| `<ModFolder>/README.md` | "Docs" button on mod row; inline rendered in preview pane |
| Repo root `README.md` | "View Docs" on registry card in Registries tab |
| `docs/*.md` | File list under "View Docs" on registry card |
| `Templates/<Game>/README.md` | Template section "View Docs" in Templates tab |
| File named `*ue4ss*` (case-insensitive) or referenced in `ue4ss.json` `docs` field | "Installation Guide" button in UE4SS setup card |

**Write relative links** using standard Markdown `[text](path)` — the app resolves them against your repo's raw content base URL. Links to other `.md` files in the same repo open inline. All external links open in the system browser.

---

## 8. Versioning Your Mods

Use [Semantic Versioning](https://semver.org) in the `version` field of `manifest.json`:

```json
{
  "mod_id": "archipelago.mygame.itemshuffle",
  "version": "1.2.0"
}
```

**Declaring dependencies** — use the `depends` field with optional semver constraints:

```json
"depends": [
  "archipelago.mygame.framework (>=1.0.0)",
  "archipelago.mygame.palschema"
]
```

**Declaring incompatibilities:**

```json
"incompatible": [
  "archipelago.mygame.legacy_items"
]
```

**Backward compatibility guidelines:**
- Bump `patch` for bug fixes that don't change `mod_id`, item names, or location names.
- Bump `minor` for new items or locations (safe addition — existing multiworlds are unaffected).
- Bump `major` for any breaking change: renamed/removed items, changed `mod_id`, logic restructuring.

> When items or locations are renamed, existing save files for in-progress multiworlds may break. Document breaking changes clearly in your `README.md`.

---

## 9. Testing and Validation

Use APF Manager's **DevTools → CI** feature to test your registry against the Archipelago apworld:

1. Add your registry URL in the **Registries tab**.
2. Open **DevTools → CI** — APF Manager builds a capabilities summary from the discovered mods.
3. Review goals and options; adjust values to reflect your intended test configuration.
4. Click **Run** — APF Manager creates a temporary GitHub Gist with your configuration and triggers the `aptests` workflow on the AP Framework repository.
5. Monitor the run from the CI tab; failures show pytest output inline.

This validates that your mod's `manifest.json` generates a valid Archipelago world with the current apworld. Run it before each release.

---

## 10. Release Checklist

Before announcing a new registry or mod version:

- [ ] `manifest.json` has correct `mod_id`, `version`, `name`, and `description`
- [ ] Framework mod has `mod_id = "archipelago.<game>.framework"` exactly
- [ ] `ue4ss.json` is present alongside the framework mod (or a UE4SS submodule is linked)
- [ ] Repo is tagged with `apf-ue4ss-registry`, `apf-ue4ss-registry-<game>`, and optionally `apf-ue4ss-registry-<game>-core`
- [ ] Root `README.md` explains what the registry provides and any prerequisites
- [ ] CI test passed against the current apworld (see Section 9)
- [ ] Breaking changes documented in `README.md` or a `CHANGELOG.md`
- [ ] Tested locally: added registry in APF Manager → Mods tab shows correct mods → Install succeeds

---

*See also: [mods.md](mods.md) · [manifest.md](manifest.md) · [templates.md](templates.md) · [dev_setup.md](dev_setup.md)*
