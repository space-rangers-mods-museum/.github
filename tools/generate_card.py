"""Generate an exhibit card README.md from the exhibit YAML and the manifest.

What this does
--------------
Reads three inputs and fills the single card template (English) that every mod
repository in the museum carries:

  * the exhibit YAML (the ``acquire`` section — the ordered chain of how the
    local archive was obtained, reproduced verbatim as it appears in the input
    YAML);
  * the ``.manifest.json`` produced by ``extract_exhibit.py`` — per-file
    SHA-256 hashes and the SHA-256 of the final archive;
  * ``ModuleInfo.txt`` inside the exhibit archive — the ``Author=`` field (for
    attribution) and the descriptions: a short one (``SmallDescriptionEng``,
    falling back to ``SmallDescription``) rendered in the card's ``Summary``
    block, and a detailed one (``FullDescriptionEng``, falling back to
    ``FullDescription``) rendered in the ``Description`` section. Blank or
    markup-only values (``<clr><clrEnd>``) count as absent and trigger the
    fallback; SRHD formatting tags are stripped so the card shows plain text.
    No placeholder is emitted — an absent description leaves its section empty.

The layout comes from the template file ``template/exhibit-card.md`` (next to this
folder's sibling); the generator only substitutes the values — the template file
is the single source of the card structure. The generator does not validate the YAML, does not recompute hashes,
and has no per-mod config.

Usage
-----
    python generate_card.py --yaml exhibits/LEOGraphicsMod.yaml \
        --manifest LEOGraphicsMod.manifest.json --zip LEOGraphicsMod.zip \
        --out ../../LEOGraphicsMod/README.md
"""
from __future__ import annotations

import argparse
import json
import re
import zipfile
from pathlib import Path

import yaml

TOOL_NAME = "generate_card.py"
TOOL_VERSION = "1.4.0"

TOOLS_DIR = Path(__file__).resolve().parent
TEMPLATE_PATH = TOOLS_DIR.parent / "template" / "exhibit-card.md"


_TAG_RE = re.compile(r"<[^>]*>")  # SRHD markup tags: <clr>, <clrEnd>, <color=...>, ...
_FIELD_RE = re.compile(r"^([A-Za-z0-9_]+)=(.*)$")  # a field line is `Key=Value`


def read_module_info(zip_path: Path) -> dict[str, list[str]]:
    """Parse ModuleInfo.txt (UTF-16 LE) from the exhibit archive.

    Returns field name -> ordered list of values. Fields repeat (``FullDescription``
    appears once per paragraph), so each key maps to every occurrence. A value runs
    from the first ``=`` to the end of the line, so it may itself contain ``=``;
    prose lines that merely contain ``=`` are not field lines and are ignored.
    """
    with zipfile.ZipFile(zip_path) as zf:
        raw = zf.read("ModuleInfo.txt")
    fields: dict[str, list[str]] = {}
    for line in raw.decode("utf-16").splitlines():
        m = _FIELD_RE.match(line)
        if m:
            fields.setdefault(m.group(1), []).append(m.group(2))
    return fields


def _meaningful(occurrences: list[str]) -> list[str]:
    """Keep only text-carrying occurrences — drop blank or markup-only ones (e.g. ``<clr><clrEnd>``).

    SRHD formatting tags are stripped so the card shows plain text paragraphs.
    """
    return [_TAG_RE.sub("", value).strip() for value in occurrences if _TAG_RE.sub("", value).strip()]


def first_field(fields: dict[str, list[str]], *names: str) -> str:
    """First text value of the first present field among ``names``, else ``""``."""
    for name in names:
        values = _meaningful(fields.get(name, []))
        if values:
            return values[0]
    return ""


def all_field(fields: dict[str, list[str]], *names: str) -> str:
    """All text occurrences of the first present field among ``names``, joined into paragraphs."""
    for name in names:
        values = _meaningful(fields.get(name, []))
        if values:
            return "\n\n".join(values)
    return ""


def extract_acquire_section(yaml_path: Path, acquire_steps: list) -> str:
    """Return the ``acquire`` section of the exhibit YAML verbatim.

    The card reproduces the acquisition route 1:1 as it appears in the input
    YAML, so the generator copies the raw text of the top-level ``acquire:``
    key and its indented block instead of re-serializing — ``yaml.dump`` would
    turn empty ``date:`` fields into ``date: null`` and reorder the keys.
    Falls back to a ``yaml.dump`` of the parsed steps if the key cannot be
    located in the raw text.
    """
    lines = yaml_path.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if line.strip() == "acquire:" and not line.startswith((" ", "\t")):
            block = [line]
            for rest in lines[i + 1:]:
                if rest == "" or rest.startswith((" ", "\t")):
                    block.append(rest)
                else:
                    break
            if len(block) > 1:
                return "\n".join(block)
            break
    # Fallback: re-serialize the parsed steps (best effort).
    if not acquire_steps:
        return ""
    return yaml.dump(acquire_steps, sort_keys=False).rstrip()


def render_files_table(files: list[dict]) -> str:
    """Render the files table (header + separator + rows) with aligned columns.

    Column widths are sized to the longest path and the SHA-256 hash, so the
    table stays aligned regardless of which files the manifest carries.
    """
    if not files:
        return ""
    width_path = max(len("file"), *(len(f["path"]) for f in files))
    width_sha = max(len("SHA-256"), *(len(f["sha256"]) for f in files))
    header = f"| {'file'.ljust(width_path)} | {'SHA-256'.ljust(width_sha)} |"
    separator = f"|{'-' * (width_path + 2)}|{'-' * (width_sha + 2)}|"
    rows = "\n".join(
        f"| {f['path'].ljust(width_path)} | {f['sha256'].ljust(width_sha)} |" for f in files
    )
    return "\n".join([header, separator, rows])


def render_card(exhibit: str, acquire_block: str, manifest: dict, author: str,
                short_desc: str, full_desc: str, template: str) -> str:
    files = manifest.get("files", [])
    archive_path = manifest.get("exhibit_archive", {}).get("path", f"{exhibit}.zip")
    archive_sha = manifest.get("exhibit_archive", {}).get("sha256", "")

    if not acquire_block.strip():
        acquire_block = "_no acquisition steps recorded_"

    files_block = render_files_table(files)

    return (
        template
        .replace("{{EXHIBIT}}", exhibit)
        .replace("{{ACQUIRE}}", acquire_block)
        .replace("{{FILES}}", files_block)
        .replace("{{ARCHIVE_PATH}}", archive_path)
        .replace("{{ARCHIVE_SHA}}", archive_sha)
        .replace("{{AUTHOR}}", author)
        .replace("{{SHORT_DESCRIPTION}}", short_desc)
        .replace("{{FULL_DESCRIPTION}}", full_desc)
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--yaml", required=True, help="path to the exhibit YAML")
    parser.add_argument("--manifest", required=True, help="path to the exhibit .manifest.json")
    parser.add_argument("--zip", required=True, help="path to the exhibit .zip (for ModuleInfo.txt)")
    parser.add_argument("--out", default="README.md", help="output path for the card README.md")
    args = parser.parse_args()

    with open(args.yaml, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    exhibit = (data.get("exhibit") or "").strip()
    if not exhibit:
        print("ERROR: YAML is missing the 'exhibit' field")
        raise SystemExit(1)
    acquire_block = extract_acquire_section(Path(args.yaml), data.get("acquire") or [])

    with open(args.manifest, encoding="utf-8") as fh:
        manifest = json.load(fh)
    fields = read_module_info(Path(args.zip))
    author = (fields.get("Author") or [""])[0].strip()
    short_desc = first_field(fields, "SmallDescriptionEng", "SmallDescription")
    full_desc = all_field(fields, "FullDescriptionEng", "FullDescription")
    template = TEMPLATE_PATH.read_text(encoding="utf-8")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        render_card(exhibit, acquire_block, manifest, author, short_desc, full_desc, template),
        encoding="utf-8",
    )
    print(f"card: {out}")
    print(f"  exhibit: {exhibit} · author: {author or '(none found)'} · acquire section: {'yes' if acquire_block.strip() else 'no'}")
    print(f"  description: short={'yes' if short_desc else 'no'} · full={'yes' if full_desc else 'no'}")


if __name__ == "__main__":
    main()
