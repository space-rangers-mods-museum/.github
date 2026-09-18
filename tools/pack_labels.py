"""Pack labels and publish ids for exhibits — all derived, never hand-written.

Every pack has one fixed label (the legend is `.ai/kb/glossary.md` in the workspace root): 🥣
`solyanka`, 🪐 `uni`, 🛰️ `redux`, 🧩 `community`. The showcase catalog shows the whole label in its
note column (`🪐 uni`) and a card shows the bare emoji in its heading (`# 🛰️ ExpSkills`), so a reader
sees where a mod came from at a glance.

Where a mod is published under a **suffixed id**:

* a mod that ships in **more than one pack** — the catalog `info/inventory.yaml` decides this — is
  published as `<mod>__<pack>` — `ExpRC__uni`, `ExpRC__redux` — and **every** of its editions carries
  the ⚠️ marker, so none of them looks like the original. The pack is a suffix on purpose: the id then
  still starts with the mod's name, and an alphabetical list keeps the editions of one mod together;
* every other exhibit keeps the mod's own id as its published id, with no marker.

Nothing of this is stored in the exhibit YAML: the pack comes from the `source` paths (that is where
the pack physically sits), the duplicate status from the packs themselves, and the published id from
those two.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

PACK_EMOJI = {
    "solyanka": "🥣",
    "uni": "🪐",
    "redux": "🛰️",
    "community": "🧩",
}

# Loose archives that sit directly in `downloaded/` — the file name names the pack.
_LOOSE_ARCHIVES = {
    "solyanka.zip": "solyanka",
    "community mods.7z": "community",
}

# Folders inside the museum that are not exhibits: the showcase repo and vendored unpackers.
NOT_EXHIBITS = {".github", "innoextract", "innounp-2"}

TOOLS_DIR = Path(__file__).resolve().parent
MUSEUM_DIR = TOOLS_DIR.parent.parent  # museum/.github/tools -> museum/
WORKSPACE = MUSEUM_DIR.parent  # the museum sits in the workspace root
CATALOG = WORKSPACE / "info" / "inventory.yaml"  # one entry per mod per pack


def pack_from_path(path: str) -> str:
    """The pack key named by one ``source`` path, or ``''`` when it cannot be told."""
    parts = [part for part in str(path).replace("\\", "/").split("/") if part]
    lowered = [part.lower() for part in parts]
    if "downloaded" in lowered:
        index = lowered.index("downloaded")
        if index + 1 < len(lowered) and lowered[index + 1] in PACK_EMOJI:
            return lowered[index + 1]
    return _LOOSE_ARCHIVES.get(lowered[-1], "") if lowered else ""


def pack_of_sources(sources: Any) -> str:
    """The pack an exhibit came from: the first pack named by its ``source`` entries."""
    for entry in sources or []:
        if isinstance(entry, dict):
            pack = pack_from_path(entry.get("path", ""))
            if pack:
                return pack
    return ""


def label(pack: str) -> str:
    """The catalog label of a pack — ``🪐 uni`` — or ``''`` for an unknown one."""
    return f"{PACK_EMOJI[pack]} {pack}" if pack in PACK_EMOJI else ""


def emoji(pack: str) -> str:
    """The bare pack emoji — ``🪐`` — or ``''`` for an unknown pack."""
    return PACK_EMOJI.get(pack, "")


def known_tokens() -> set[str]:
    """Every token the pack label and the duplicate marker can put into the note column."""
    tokens = {"⚠️"}
    for pack, mark in PACK_EMOJI.items():
        tokens.update({mark, pack})
    return tokens


def yaml_of(folder: str, mod_id: str) -> dict:
    """Read an exhibit's YAML from its museum folder (``{}`` when it is not there)."""
    yaml_path = MUSEUM_DIR / folder / f"{mod_id}.yaml"
    try:
        return yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}


def pack_of_exhibit(folder: str, mod_id: str) -> str:
    """The pack an exhibit came from, read from its own YAML's ``source`` paths."""
    return pack_of_sources(yaml_of(folder, mod_id).get("source"))


def pack_for_exhibit(mod_id: str, stored_id: str) -> str:
    """The pack of an exhibit named by ``stored_id``, which may be stale after a folder rename.

    Tries the stored id as a folder, then the same id under the other convention
    (``pack__mod`` → ``mod__pack``, the earlier naming), then the museum's own exhibits of that mod
    when exactly one is left — so an id written before a rename still resolves to its pack.
    """
    pack = pack_of_exhibit(stored_id, mod_id)
    if pack:
        return pack
    if stored_id.endswith(f"__{mod_id}"):
        pack = pack_of_exhibit(f"{mod_id}__{stored_id[: -len(mod_id) - 2]}", mod_id)
        if pack:
            return pack
    candidates = exhibits_of(mod_id)
    return candidates[0][0] if len(candidates) == 1 else ""


def exhibits_of(mod_id: str) -> list[tuple[str, str]]:
    """Every museum exhibit of one mod: ``(pack, folder)`` for each folder holding its YAML."""
    found: list[tuple[str, str]] = []
    for folder in sorted(MUSEUM_DIR.iterdir()):
        yaml_path = folder / f"{mod_id}.yaml"
        if not folder.is_dir() or folder.name in NOT_EXHIBITS or not yaml_path.is_file():
            continue
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
        found.append((pack_of_sources(data.get("source")), folder.name))
    return found


_CATALOG_ENTRIES: list[dict] | None = None


def catalog() -> list[dict]:
    """The workspace's mod catalog, ``info/inventory.yaml`` — one entry per mod per pack.

    Read once per run; an unreadable file (a checkout outside the workspace) yields an empty list,
    and callers fall back to the museum's own exhibit set.
    """
    global _CATALOG_ENTRIES
    if _CATALOG_ENTRIES is None:
        try:
            _CATALOG_ENTRIES = yaml.safe_load(CATALOG.read_text(encoding="utf-8")) or []
        except (OSError, yaml.YAMLError):
            _CATALOG_ENTRIES = []
    return _CATALOG_ENTRIES


def packs_holding(mod_id: str) -> list[str]:
    """Which packs ship a mod folder named ``mod_id``, sorted.

    Read from the catalog (`info/inventory.yaml`, generated from the packs' own `ModuleInfo.txt`):
    every entry carries the mod's `Folder` and the pack it was read from in `note`, so the packs a
    mod ships in are simply the entries sharing that folder.
    """
    packs = set()
    for entry in catalog():
        if str(entry.get("Folder") or "") != mod_id:
            continue
        note = str(entry.get("note") or "").split()
        pack = note[-1] if note else ""
        if pack in PACK_EMOJI:
            packs.add(pack)
    return sorted(packs)


def packs_in_museum(mod_id: str) -> list[str]:
    """The packs the museum exhibits one mod from, sorted and de-duplicated."""
    return sorted({pack for pack, _folder in exhibits_of(mod_id) if pack})


def packs_of(mod_id: str) -> list[str]:
    """The packs that ship a mod: the workspace's packs, or — outside the workspace, where there
    are none to read — the packs the museum itself exhibits it from."""
    return packs_holding(mod_id) or packs_in_museum(mod_id)


def is_duplicate(mod_id: str) -> bool:
    """True when the mod ships in more than one pack (so every edition needs a pack suffix)."""
    return len(packs_of(mod_id)) > 1


def github_id(mod_id: str, pack: str) -> str:
    """The id an exhibit is published under — ``<mod>__<pack>`` for a duplicated mod, else the mod's.

    The pack is a suffix, so the id still sorts under the mod's own name.
    """
    return f"{mod_id}__{pack}" if pack and is_duplicate(mod_id) else mod_id
