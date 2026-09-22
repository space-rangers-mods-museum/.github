"""Update the museum showcase (.csv + main page README) with a published exhibit.

What this does
--------------
Records an exhibit in the museum mod list ``exhibits.csv`` (one row per exhibit)
and rebuilds the showcase main page ``README.md`` from that ``.csv``: the
``.csv`` is the single source of the catalog, the page is generated from it and
never hand-edited. Called by the ``publish_exhibit.py`` orchestrator as the
showcase-local step, or directly for a standalone update.

The row columns (in order) are ``mod_name``, ``mod_author``,
``mod_museum_repo_name``, ``mod_museum_repo_link``, ``mod_summary``,
``mod_github_id``, ``mod_note``. ``mod_museum_repo_name`` is the mod's own id (no suffix),
``mod_github_id`` the repository/artifact id it is published under — derived: a
mod that ships in more than one pack is published as ``<mod>__<pack>``
(``ExpRC__uni``, ``ExpRC__redux``), every other mod under its own id. The link and
the row's de-duplication key are the
``mod_github_id``; the Exhibit column of the page links to it and shows that id
(``[ExpRC__redux](…/ExpRC__redux)``), and ``mod_note`` carries the pack label (``🪐 uni``) plus, for
a duplicated mod, the ⚠️ marker — both derived (the pack from the exhibit YAML's ``source`` paths,
the marker from the packs the mod ships in). Text written by hand in that cell is kept after them.
``mod_author`` and
``mod_summary`` are read from the exhibit's generated card ``README.md`` (the
single source of those values, in turn built from ``ModuleInfo.txt``) rather
than asked for on the command line. If the repository id is already present
in the ``.csv`` the row is not duplicated — the tool only fills in gaps
(including a missing author/summary) and then regenerates the page, so it is
safe to run repeatedly.

The page layout comes from the template file ``template/showcase-readme.md``;
the tool only substitutes the catalog rows into the ``{{ROWS}}`` placeholder.
The same rendered page is also mirrored to ``profile/README.md``, which is
what GitHub displays on the organization profile page (the root ``README.md``
only renders when visiting the repo itself). In that copy relative image
``src`` and relative file links are rewritten to absolute GitHub URLs, because
``profile/README.md`` lives one directory deeper than the root README.

Usage
-----
    python update_showcase.py --exhibit LEOGraphicsMod
    python update_showcase.py --exhibit LEOGraphicsMod --name "LEO Graphics Mod"
"""
from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

import pack_labels

TOOL_NAME = "update_showcase.py"
TOOL_VERSION = "1.6.0"
DEFAULT_ORG = "space-rangers-mods-museum"
DEFAULT_HEADER = [
    "mod_name",
    "mod_author",
    "mod_museum_repo_name",
    "mod_museum_repo_link",
    "mod_summary",
    "mod_github_id",
    "mod_note",
]
# The catalog note of a duplicate edition (the same mod published from more than one pack).
DUPLICATE_NOTE = "⚠️"


def note_for(mod_id: str, github_id: str, pack: str = "") -> str:
    """Catalog note of an exhibit: the pack label, plus ⚠️ when the mod has a duplicate edition.

    Both parts are derived — the pack from the exhibit's ``source`` paths, the marker from the packs
    the mod ships in (a mod in more than one pack is a duplicate, and **every** of its editions is
    marked) — so the note cannot drift from the exhibit. Text written by hand in the cell is
    preserved by :func:`merge_note`.
    """
    parts = [DUPLICATE_NOTE] if pack_labels.is_duplicate(mod_id) else []
    label = pack_labels.label(pack)
    if label:
        parts.append(label)
    return " ".join(parts)


def merge_note(existing: str, mod_id: str, github_id: str, pack: str) -> str:
    """Recompose a note cell: the derived parts first, then whatever was written by hand."""
    hand = " ".join(token for token in existing.split() if token not in pack_labels.known_tokens())
    return " ".join(part for part in (note_for(mod_id, github_id, pack), hand) if part)

TOOLS_DIR = Path(__file__).resolve().parent
SHOWCASE_DIR = TOOLS_DIR.parent
MUSEUM_DIR = SHOWCASE_DIR.parent
TEMPLATE_PATH = SHOWCASE_DIR / "template" / "showcase-readme.md"
PROFILE_README_PATH = SHOWCASE_DIR / "profile" / "README.md"

AUTHOR_RE = re.compile(r"^\*\s+\*\*Author:\*\*\s*(.*)$")


def _col(header: list[str], name: str) -> int:
    return header.index(name) if name in header else -1


def load_rows(csv_path: Path) -> tuple[list[str], list[list[str]]]:
    """Read the header and non-empty data rows from the showcase .csv."""
    with csv_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        header = next(reader, None) or []
        rows = [row for row in reader if row and any(cell.strip() for cell in row)]
    return header, rows


def save_rows(csv_path: Path, header: list[str], rows: list[list[str]]) -> None:
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(rows)


def read_card_exhibit_summary(exhibit: str) -> tuple[str, str]:
    """Read ``Author`` and ``Summary`` from the exhibit's generated card README.

    Returns ``(author, summary)``; empty strings when the card is missing or a
    field is absent. The card is the single source of these values (it is built
    from ``ModuleInfo.txt`` + the manifest), so the showcase inherits them from
    there instead of asking for manual input.
    """
    card_path = MUSEUM_DIR / exhibit / "README.md"
    try:
        lines = card_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return "", ""

    author = ""
    summary_parts: list[str] = []
    in_summary = False
    for line in lines:
        if not author:
            m = AUTHOR_RE.match(line)
            if m:
                author = m.group(1).strip()
        stripped = line.strip()
        if stripped == "### Summary":
            in_summary = True
            continue
        if in_summary:
            if stripped == "":
                continue  # blank line right after the heading
            if stripped.startswith("#") or re.fullmatch(r"([-*_])\1{2,}", stripped):
                break  # reached the next section (e.g. "## " heading or a "---" rule)
            summary_parts.append(stripped)
    return author, " ".join(summary_parts)


def build_rows_block(header: list[str], rows: list[list[str]]) -> str:
    """Render the catalog rows into the markdown table body for {{ROWS}}.

    The Exhibit column links to the repository the edition is published in — its `mod_github_id`,
    which carries the pack suffix for a duplicated mod (`ExpRC__redux`) — and shows that id as the
    link text: the suffix is what the ⚠️ marker and the pack label in the Note column expand on.
    """
    i_name, i_author = _col(header, "mod_name"), _col(header, "mod_author")
    i_summary = _col(header, "mod_summary")
    i_repo, i_link = _col(header, "mod_museum_repo_name"), _col(header, "mod_museum_repo_link")
    i_gh = _col(header, "mod_github_id")
    i_note = _col(header, "mod_note")

    def cell(row: list[str], i: int) -> str:
        return row[i].strip() if 0 <= i < len(row) else ""

    def exhibit_cell(row: list[str]) -> str:
        label = cell(row, i_gh) or cell(row, i_repo)
        url = cell(row, i_link) or f"https://github.com/{DEFAULT_ORG}/{label}"
        return f"[{label}]({url})"

    return "\n".join(
        f"| {cell(row, i_name)} | {cell(row, i_author)} "
        f"| {exhibit_cell(row)} | {cell(row, i_note)} | {cell(row, i_summary)} |"
        for row in rows
    )


_IMG_SRC_RE = re.compile(r'src="([^"]+)"')
_MD_LINK_RE = re.compile(r'(!?\[[^\]]*\]\()([^)]+)(\))')


def _profile_url(target: str, org: str, raw: bool) -> str:
    """Return an absolute GitHub URL for a relative path referenced from profile/README.md.

    ``profile/README.md`` lives one directory deeper than the root README, so
    a relative reference that resolves in the root README breaks there. Rewrite
    it to an absolute URL — raw for images, blob for file links. Already
    absolute targets (http(s), anchors, root-absolute) are returned unchanged.
    """
    if target.startswith(("http:", "https:", "#", "/")):
        return target
    branch = "main"
    if raw:
        return f"https://raw.githubusercontent.com/{org}/.github/{branch}/{target}"
    return f"https://github.com/{org}/.github/blob/{branch}/{target}"


def render_profile_readme(readme: str, org: str) -> str:
    """Mirror the root showcase so it also renders as the organization profile page.

    GitHub shows the org profile from ``profile/README.md`` in the ``.github``
    repo. This rewrites relative image ``src`` attributes and relative file
    links in the rendered root README to absolute GitHub URLs so the profile
    copy renders the same content one directory deeper. Markdown image links
    (``![..](..)``) are left untouched.
    """
    out = _IMG_SRC_RE.sub(
        lambda m: f'src="{_profile_url(m.group(1), org, raw=True)}"', readme
    )
    return _MD_LINK_RE.sub(_link_sub(org), out)


def _link_sub(org: str):
    def _rewrite(m: re.Match[str]) -> str:
        if m.group(1).startswith("!["):
            return m.group(0)
        target = m.group(2)
        if target.startswith(("http:", "https:", "#", "/")):
            return m.group(0)
        return f"{m.group(1)}{_profile_url(target, org, raw=False)}{m.group(3)}"

    return _rewrite


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--exhibit", required=True, help="museum repo id of the exhibit — the github_id (folder + repository name)")
    parser.add_argument("--mod-id", help="the mod's own id, without the pack suffix (default: same as --exhibit)")
    parser.add_argument("--name", help="display mod name (default: the mod id)")
    parser.add_argument("--org", default=DEFAULT_ORG, help=f"museum org (default: {DEFAULT_ORG})")
    parser.add_argument("--csv", default=str(SHOWCASE_DIR / "exhibits.csv"), help="path to the museum mod list .csv")
    parser.add_argument("--readme", default=str(SHOWCASE_DIR / "README.md"), help="path to the showcase main page README.md")
    parser.add_argument("--profile-readme", default=str(PROFILE_README_PATH), help="path to the org profile README.md (default: <showcase>/profile/README.md)")
    args = parser.parse_args()

    exhibit = args.exhibit.strip()
    if not exhibit:
        print("ERROR: --exhibit must not be empty")
        raise SystemExit(1)
    mod_id = (args.mod_id or exhibit).strip() or exhibit
    name = (args.name or mod_id).strip() or mod_id
    # The published id is derived, not taken on trust: a mod the museum holds from more than one
    # pack is published as `<mod>__<pack>` for every one of those editions. `--exhibit` names the
    # exhibit's museum folder — where its YAML and its card are read from.
    folder = exhibit
    exhibit_pack = pack_labels.pack_of_exhibit(folder, mod_id)
    if pack_labels.github_id(mod_id, exhibit_pack) != exhibit:
        exhibit = pack_labels.github_id(mod_id, exhibit_pack)
        print(f"showcase: the folder is {folder!r}, the mod is published as {exhibit!r} — rename the folder to match")
    link = f"https://github.com/{args.org}/{exhibit}"

    csv_path = Path(args.csv)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    header, rows = load_rows(csv_path)
    if not header:
        header = DEFAULT_HEADER

    i_author, i_summary = _col(header, "mod_author"), _col(header, "mod_summary")
    i_repo = _col(header, "mod_museum_repo_name")
    i_link = _col(header, "mod_museum_repo_link")
    i_gh = _col(header, "mod_github_id")
    if i_gh < 0:  # a .csv written before the column existed — keep the repo-name column authoritative
        i_gh = i_repo
    i_note = _col(header, "mod_note")

    # Normalize rows to the header length so later indexing is always safe.
    for row in rows:
        if len(row) < len(header):
            row.extend([""] * (len(header) - len(row)))

    # Backfill missing author/summary for existing rows from their cards.
    for row in rows:
        exhibit_id = row[i_gh].strip() or row[i_repo].strip()
        if exhibit_id and (not row[i_author].strip() or not row[i_summary].strip()):
            author, summary = read_card_exhibit_summary(exhibit_id)
            if not row[i_author].strip():
                row[i_author] = author
            if not row[i_summary].strip():
                row[i_summary] = summary

    # Recompute the derived parts of every row: the pack (from the exhibit YAML's source paths),
    # the published id — `<mod>__<pack>` for a mod that ships in more than one pack — its link, and
    # the note cell. Text written by hand in the note survives after them. A row whose exhibit
    # cannot be found at all (its folder is gone) is left untouched.
    derived_ids: set[str] = set()
    for row in rows:
        row_mod_id = row[i_repo].strip()
        if not row_mod_id:
            continue
        stored_id = row[i_gh].strip() or row_mod_id
        row_pack = pack_labels.pack_for_exhibit(row_mod_id, stored_id)
        if not row_pack:
            derived_ids.add(stored_id)
            continue
        row_github_id = pack_labels.github_id(row_mod_id, row_pack)
        derived_ids.add(row_github_id)
        if row_github_id != row[i_gh].strip():
            row[i_gh] = row_github_id
            row[i_link] = f"https://github.com/{args.org}/{row_github_id}"
        if i_note >= 0:
            row[i_note] = merge_note(row[i_note], row_mod_id, row_github_id, row_pack)

    # Append a new row if this exhibit is not yet catalogued. The key is the published id — matching
    # by the mod id would fuse the two editions of a duplicated mod into one row.
    if exhibit not in derived_ids:
        author, summary = read_card_exhibit_summary(folder)
        row = [""] * len(header)
        row[_col(header, "mod_name")] = name
        row[i_author] = author
        row[i_summary] = summary
        row[i_repo] = mod_id
        row[i_gh] = exhibit
        row[i_link] = link
        if i_note >= 0:
            row[i_note] = note_for(mod_id, exhibit, exhibit_pack)
        rows.append(row)
        print(f"showcase: adding row {name!r} (mod id {mod_id}, github_id {exhibit})")

    # Keep the catalog alphabetical by the mod's own name, then by the published id: the editions of
    # one mod (its duplicates) land next to each other, which is the point of the ⚠️ marker and the
    # pack label beside them.
    rows.sort(key=lambda row: (row[i_repo].strip().lower(), row[i_gh].strip()))

    save_rows(csv_path, header, rows)

    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    readme = template.replace("{{ROWS}}", build_rows_block(header, rows))
    readme_path = Path(args.readme)
    readme_path.parent.mkdir(parents=True, exist_ok=True)
    readme_path.write_text(readme, encoding="utf-8")

    profile_path = Path(args.profile_readme)
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(render_profile_readme(readme, args.org), encoding="utf-8")

    print(f"showcase: {csv_path} ({len(rows)} exhibit(s))")
    print(f"showcase: {readme_path}")
    print(f"showcase: {profile_path}")


if __name__ == "__main__":
    main()
