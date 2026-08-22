"""Extract a mod from its original source and repack it as a clean exhibit.

What this does
--------------
Mods ship in one of two forms, and we extract the mod folder from either:

  1. a .zip archive     -> read directly (stdlib)
  2. an installer .exe  -> opened with 7-Zip into a temp folder

Then we repack ONLY the mod's folder into a standalone .zip whose root is the
mod itself (ModuleInfo.txt at the top level, no wrapper folder). Packing is
always the same and deterministic: fixed compression level, sorted entries,
one fixed timestamp, fixed file mode and zip metadata. Same source + same
arguments => byte-identical exhibit .zip every time.

Besides the exhibit .zip we write a .manifest.json with per-file hashes and
the SHA-256 of the final archive (no separate .sha256 file — the archive hash
lives in the manifest).

Usage
-----
    python extract_exhibit.py --exhibit LEOGraphicsMod \
        --mod-dir Mods/Solyanka/LEOGraphicsMod \
        --source Solyanka.zip --out-dir ../../LEOGraphicsMod

    # optionally pin the source so a wrong archive fails loudly:
    ... --source-sha256 42a78494c3a61b867b88c313e02d6f234caf85af847dc891d1d86b3450b18dd8
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

TOOL_NAME = "extract_exhibit.py"
TOOL_VERSION = "0.2.0"

# Fixed values so the same input always yields the same exhibit zip.
EXHIBIT_TIMESTAMP = (1980, 1, 1, 0, 0, 0)  # single normalized mtime for all entries
COMPRESS_LEVEL = 6


def sha256_of(path: Path) -> str:
    """SHA-256 of a file, read in chunks so it works for large archives."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_exhibit(
    exhibit: str,
    source: Path,
    out_dir: Path,
    mod_dir: str,
    expected_sha: str | None,
) -> dict:
    """Extract mod_dir from source and repack it flat (ModuleInfo.txt at root)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    out_zip = out_dir / f"{exhibit}.zip"

    # 1. Optional sanity check that we are reading the expected source archive.
    source_sha = sha256_of(source)
    if expected_sha and source_sha != expected_sha:
        raise RuntimeError(
            f"source SHA-256 mismatch for {source}:\n"
            f"  got      {source_sha}\n"
            f"  expected {expected_sha}"
        )

    # 2. Open the source: a .zip in-process, an installer .exe via 7-Zip.
    if source.suffix.lower() == ".zip":
        src_zip = zipfile.ZipFile(source)
        entries = ((info.filename, info.is_dir(), info) for info in src_zip.infolist())
        close = src_zip.close
    else:
        # 7-Zip can open most installers (Inno Setup, NSIS, ...).
        if shutil.which("7z") is None:
            raise RuntimeError(
                "7z executable not found on PATH; install 7-Zip to open installer sources"
            )
        tmp = tempfile.mkdtemp(prefix="exhibit_")
        subprocess.run(["7z", "x", "-y", f"-o{tmp}", str(source)], check=True)
        entries = (
            (p.relative_to(tmp).as_posix(), p.is_dir(), p) for p in sorted(tmp.rglob("*"))
        )

        def close() -> None:
            shutil.rmtree(tmp, ignore_errors=True)

    # 3. Keep only files under mod_dir, stripped of the prefix so the exhibit
    #    root is the mod itself (ModuleInfo.txt lands at the top level).
    prefix = mod_dir.rstrip("/") + "/"
    files: dict[str, object] = {}
    file_sizes: dict[str, int] = {}
    try:
        for arcname, is_dir, info in entries:
            if is_dir or not arcname.startswith(prefix):
                continue
            out_name = arcname[len(prefix):]
            if not out_name:
                continue
            if isinstance(info, zipfile.ZipInfo):  # read from the source zip
                files[out_name] = lambda info=info: src_zip.open(info)
            else:  # read from the 7-Zip temp folder
                files[out_name] = lambda info=info: info.open("rb")
            file_sizes[out_name] = (
                info.file_size if isinstance(info, zipfile.ZipInfo) else info.stat().st_size
            )
    finally:
        if not files:
            close()
    if not files:
        raise RuntimeError(f"no files found under {mod_dir!r} in {source}")

    # 4. Write the deterministic exhibit zip (source still open so we can read it).
    file_hashes: dict[str, str] = {}
    with zipfile.ZipFile(
        out_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=COMPRESS_LEVEL
    ) as zf:
        for out_name in sorted(files):
            zinfo = zipfile.ZipInfo(filename=out_name, date_time=EXHIBIT_TIMESTAMP)
            zinfo.compress_type = zipfile.ZIP_DEFLATED
            zinfo.external_attr = 0o644 << 16  # fixed unix file mode
            zinfo.create_system = 3            # normalize cross-OS zip metadata
            with zf.open(zinfo, "w") as dst:
                h = hashlib.sha256()
                with files[out_name]() as src:
                    for chunk in iter(lambda: src.read(1 << 20), b""):
                        h.update(chunk)
                        dst.write(chunk)
                file_hashes[out_name] = h.hexdigest()

    # 5. Close the source now that we are done reading it.
    close()

    # 6. Write the manifest (archive hash + per-file hashes + source info).
    archive_sha = sha256_of(out_zip)
    manifest = {
        "exhibit_name": exhibit,
        "source": {
            "archive": source.name,
            "size": source.stat().st_size,
            "sha256": source_sha,
        },
        "exhibit_archive": {
            "path": out_zip.name,
            "size": out_zip.stat().st_size,
            "sha256": archive_sha,
            "entries": len(files),
        },
        "files": [
            {"path": p, "size": file_sizes[p], "sha256": file_hashes[p]}
            for p in sorted(file_hashes)
        ],
    }
    (out_dir / f"{exhibit}.manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--exhibit", required=True, help="exhibit / mod id")
    parser.add_argument(
        "--mod-dir",
        required=True,
        help="in-archive path to the mod folder, e.g. Mods/Solyanka/LEOGraphicsMod",
    )
    parser.add_argument("--source", required=True, help="path to the source (.zip or installer .exe)")
    parser.add_argument("--out-dir", required=True, help="directory for the exhibit archive + hashes")
    parser.add_argument("--source-sha256", help="expected source SHA-256 (reproducibility check)")
    args = parser.parse_args()

    try:
        manifest = build_exhibit(
            args.exhibit,
            Path(args.source),
            Path(args.out_dir),
            args.mod_dir,
            args.source_sha256,
        )
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        raise SystemExit(1)

    print(
        f"{manifest['exhibit_name']}: {manifest['exhibit_archive']['path']} "
        f"({manifest['exhibit_archive']['entries']} files, {manifest['exhibit_archive']['size']} bytes)"
    )
    print(f"  SHA-256: {manifest['exhibit_archive']['sha256']}")
    print(f"  manifest: {Path(args.out_dir) / (manifest['exhibit_name'] + '.manifest.json')}")


if __name__ == "__main__":
    main()
