"""Publish an exhibit to the museum — one command for the whole chain.

What this does
--------------
Reads a single exhibit YAML and runs the publish chain in strict order, writing
a log line for every step and stopping on the first failed step:

  1. resolve the source — if ``source.path`` is a URL (e.g. a google disk link),
     download it to a temp file; if it is an existing local path, use it as-is;
  2. extract and repack the mod folder (``extract_exhibit.py``);
  3. generate the card README (``generate_card.py``);
  4. form the local repository folder (card + a copy of the exhibit YAML +
     manifest; the archive is excluded via ``.gitignore`` — it is a release
     asset, not a source file in the repo);
  5. publish the repository through ``gh`` (repo create + push);
  6. publish the final archive as a GitHub release (``gh release create``,
     version always ``v1.0.0``, title = exhibit name) and delete the local
     ``.zip`` — it now lives as the release asset only.

Pass ``--no-publish`` to run steps 1-5 only (extract -> card -> repo-folder
check) without touching ``gh`` or the git repository — useful for a local
verification run.

Usage
-----
    python publish_exhibit.py exhibits/LEOGraphicsMod.yaml \
        --out-dir ../../LEOGraphicsMod

    # local-only run (no gh, no git):
    python publish_exhibit.py exhibits/LEOGraphicsMod.yaml \
        --out-dir ./build --no-publish
"""
from __future__ import annotations

import argparse
import datetime as _dt
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

import yaml

TOOL_NAME = "publish_exhibit.py"
TOOL_VERSION = "1.0.0"
DEFAULT_ORG = "space-rangers-mods-museum"
RELEASE_VERSION = "v1.0.0"  # archive versioning is out of scope — always v1.0.0

TOOLS_DIR = Path(__file__).resolve().parent


class StepFailed(RuntimeError):
    """A pipeline step failed; the chain must stop here."""


def log_write(log_path: Path, line: str) -> None:
    ts = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(f"[{ts}] {line}\n")


def run_step(log_path: Path, name: str, argv: list[str]) -> None:
    """Run a step, log it, and stop the chain on failure."""
    log_write(log_path, f"STEP {name}: {' '.join(argv)}")
    print(f"[{name}] {' '.join(argv)}")
    try:
        result = subprocess.run(argv, check=False, capture_output=True, text=True)
    except OSError as exc:
        log_write(log_path, f"FAIL {name}: cannot run: {exc}")
        raise StepFailed(f"cannot run step '{name}': {exc}")
    if result.stdout:
        log_write(log_path, "  " + result.stdout.strip().replace("\n", "\n  "))
        print(result.stdout.rstrip())
    if result.returncode != 0:
        err = result.stderr.strip()
        log_write(log_path, f"FAIL {name}: exit {result.returncode}: {err}")
        if err:
            print(err, file=sys.stderr)
        raise StepFailed(f"step '{name}' failed (exit {result.returncode})")


def resolve_source(source_path: str, yaml_dir: Path, log_path: Path, work_dir: Path) -> Path:
    """Return a local path to the source.

    A URL (http/https) is downloaded to a temp file. A relative path is
    resolved against the exhibit YAML's directory, so the command works from
    any CWD.
    """
    if source_path.startswith(("http://", "https://")):
        log_write(log_path, f"STEP download source: {source_path}")
        print(f"[download source] {source_path}")
        local = work_dir / "source.download"
        try:
            urllib.request.urlretrieve(source_path, local)
        except Exception as exc:  # noqa: BLE001 — stop the chain on any failure
            log_write(log_path, f"FAIL download source: {exc}")
            raise StepFailed(f"failed to download source: {exc}")
        log_write(log_path, f"OK download source -> {local} ({local.stat().st_size} bytes)")
        print(f"[download source] -> {local} ({local.stat().st_size} bytes)")
        return local
    path = Path(source_path)
    if not path.is_absolute():
        path = yaml_dir / path
    if not path.exists():
        raise StepFailed(f"source path does not exist: {source_path}")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("yaml_path", help="path to the exhibit YAML")
    parser.add_argument("--out-dir", help="local repository folder for the exhibit (default: <museum working dir>/<exhibit>, flat next to .github)")
    parser.add_argument("--org", default=DEFAULT_ORG, help=f"museum org (default: {DEFAULT_ORG})")
    parser.add_argument("--no-publish", action="store_true", help="run extract -> card -> folder only (no gh, no git)")
    parser.add_argument("--log", help="path to the pipeline log file (default: <out-dir>/publish.log)")
    args = parser.parse_args()

    with open(args.yaml_path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    exhibit = (data.get("exhibit") or "").strip()
    if not exhibit:
        print("ERROR: YAML is missing the 'exhibit' field")
        raise SystemExit(1)
    source = data.get("source") or {}
    source_path = (source.get("path") or "").strip()
    source_target = (source.get("target") or "").strip()
    if not source_path or not source_target:
        print("ERROR: YAML is missing 'source.path' / 'source.target'")
        raise SystemExit(1)

    # Default out-dir: the museum working dir (parent of the .github showcase repo),
    # so exhibit repos sit flat next to .github — never nested inside the showcase repo.
    out_dir = Path(args.out_dir) if args.out_dir else Path(TOOLS_DIR).parent.parent / exhibit
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = Path(args.log) if args.log else out_dir / "publish.log"

    log_write(log_path, f"START publish {exhibit} ({TOOL_NAME} {TOOL_VERSION})")
    print(f"publish {exhibit}: chain start")

    work_dir = Path(tempfile.mkdtemp(prefix=f"publish_{exhibit}_"))
    yaml_dir = Path(args.yaml_path).resolve().parent

    # 1. Resolve the source (download if URL, else local path).
    local_source = resolve_source(source_path, yaml_dir, log_path, work_dir)

    # 2. Extract and repack.
    run_step(
        log_path,
        "extract",
        [
            sys.executable, str(TOOLS_DIR / "extract_exhibit.py"),
            "--exhibit", exhibit,
            "--mod-dir", source_target,
            "--source", str(local_source),
            "--out-dir", str(out_dir),
        ],
    )

    # 3. Generate the card README.
    run_step(
        log_path,
        "card",
        [
            sys.executable, str(TOOLS_DIR / "generate_card.py"),
            "--yaml", str(Path(args.yaml_path)),
            "--manifest", str(out_dir / f"{exhibit}.manifest.json"),
            "--zip", str(out_dir / f"{exhibit}.zip"),
            "--out", str(out_dir / "README.md"),
        ],
    )

    # 4. Copy the exhibit YAML into the repo folder — it records where the
    #    instance came from and lives with the exhibit.
    shutil.copy2(args.yaml_path, out_dir / Path(args.yaml_path).name)

    # 5. Local repository folder — the source files of the exhibit. The archive
    #    is intentionally NOT part of it: it ships as a release asset instead.
    required = ["README.md", Path(args.yaml_path).name, f"{exhibit}.manifest.json"]
    missing = [name for name in required if not (out_dir / name).exists()]
    if missing:
        log_write(log_path, f"FAIL repo-folder: missing {missing}")
        raise StepFailed(f"repository folder incomplete, missing: {missing}")
    log_write(log_path, f"OK repo-folder: {out_dir} ({', '.join(required)})")
    print(f"[repo-folder] {out_dir}")
    shutil.rmtree(work_dir, ignore_errors=True)

    if args.no_publish:
        log_write(log_path, "DONE (no-publish): chain stopped after repo-folder")
        print("no-publish: stopped after repo-folder — gh/git steps skipped")
        return

    # Keep the archive and the pipeline log out of the git repo — the archive is
    # published as a release asset, not committed as a source file.
    (out_dir / ".gitignore").write_text("*.zip\npublish.log\n", encoding="utf-8")

    # 6. Publish the repository through gh.
    run_step(
        log_path,
        "gh-create-repo",
        ["gh", "repo", "create", f"{args.org}/{exhibit}", "--public", "--source", str(out_dir), "--push"],
    )

    # 7. Publish the archive as a release (version always v1.0.0, title = exhibit).
    run_step(
        log_path,
        "gh-release",
        ["gh", "release", "create", RELEASE_VERSION, "--title", exhibit, str(out_dir / f"{exhibit}.zip")],
    )

    # 8. The archive now lives as the GitHub release asset — remove the local
    #    copy so it does not linger in the repo folder as a source file.
    (out_dir / f"{exhibit}.zip").unlink(missing_ok=True)

    log_write(log_path, "DONE publish complete")
    print(f"publish {exhibit}: done")


if __name__ == "__main__":
    try:
        main()
    except StepFailed as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
