"""Update the museum showcase (.csv + main page README) with a published exhibit.

What this does
--------------
Records an exhibit in the museum mod list ``exhibits.csv`` (one row per exhibit)
and rebuilds the showcase main page ``README.md`` from that ``.csv``: the
``.csv`` is the single source of the catalog, the page is generated from it and
never hand-edited. Called by the ``publish_exhibit.py`` orchestrator as the
showcase-local step, or directly for a standalone update.

The row columns (in order) are ``mod_name``, ``mod_museum_repo_name``,
``mod_museum_repo_link``. If the repository name is already present in the
``.csv`` the row is not duplicated — the tool only fills in gaps and then
regenerates the page, so it is safe to run repeatedly.

The page layout comes from the template file ``template/showcase-readme.md``;
the tool only substitutes the catalog rows into the ``{{ROWS}}`` placeholder.

Usage
-----
    python update_showcase.py --exhibit LEOGraphicsMod
    python update_showcase.py --exhibit LEOGraphicsMod --name "LEO Graphics Mod"
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

TOOL_NAME = "update_showcase.py"
TOOL_VERSION = "1.0.0"
DEFAULT_ORG = "space-rangers-mods-museum"
DEFAULT_HEADER = ["mod_name", "mod_museum_repo_name", "mod_museum_repo_link"]

TOOLS_DIR = Path(__file__).resolve().parent
SHOWCASE_DIR = TOOLS_DIR.parent
TEMPLATE_PATH = SHOWCASE_DIR / "template" / "showcase-readme.md"


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


def build_rows_block(rows: list[list[str]]) -> str:
    """Render the catalog rows into the markdown table body for {{ROWS}}."""
    return "\n".join(f"| {row[0]} | [{row[1]}]({row[2]}) |" for row in rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--exhibit", required=True, help="museum repo id of the exhibit (same as the repo name)")
    parser.add_argument("--name", help="display mod name (default: same as --exhibit)")
    parser.add_argument("--org", default=DEFAULT_ORG, help=f"museum org (default: {DEFAULT_ORG})")
    parser.add_argument("--csv", default=str(SHOWCASE_DIR / "exhibits.csv"), help="path to the museum mod list .csv")
    parser.add_argument("--readme", default=str(SHOWCASE_DIR / "README.md"), help="path to the showcase main page README.md")
    args = parser.parse_args()

    exhibit = args.exhibit.strip()
    if not exhibit:
        print("ERROR: --exhibit must not be empty")
        raise SystemExit(1)
    name = (args.name or exhibit).strip() or exhibit
    link = f"https://github.com/{args.org}/{exhibit}"

    csv_path = Path(args.csv)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    header, rows = load_rows(csv_path)
    if not header:
        header = DEFAULT_HEADER

    repo_col = 1
    if not any(len(row) > repo_col and row[repo_col].strip() == exhibit for row in rows):
        rows.append([name, exhibit, link])
        print(f"showcase: adding row {name!r} ({exhibit})")

    save_rows(csv_path, header, rows)

    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    readme = template.replace("{{ROWS}}", build_rows_block(rows))
    readme_path = Path(args.readme)
    readme_path.parent.mkdir(parents=True, exist_ok=True)
    readme_path.write_text(readme, encoding="utf-8")

    print(f"showcase: {csv_path} ({len(rows)} exhibit(s))")
    print(f"showcase: {readme_path}")


if __name__ == "__main__":
    main()
