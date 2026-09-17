"""Extract a mod from one or more original sources and repack it as a clean exhibit.

What this does
--------------
A mod can ship across several sources, each carrying a different part of it:
the full-game installer ``.exe`` holds the complete mod tree (with
``ModuleInfo.txt``), while an update ``.zip`` holds newer files that replace
part of that tree. Every source is one of:

  1. a .zip archive      -> read directly (stdlib)
  2. an installer .exe   -> opened with innoextract, or with innounp when the installer is
                            newer than innoextract understands (REDUX is Inno Setup 6.4.3)
  3. a .7z archive       -> read with py7zr; the pack overlays ("Universe Redux Fixes.7z")
                            are applied to the unpacked pack, so they come last in the list

``source`` is therefore an ordered LIST. Each source's mod folder is extracted
in order into a shared staging area, and a later source's file OVERWRITES an
earlier one with the same relative path. This gives a complete merged mod:
installer first (base, contains ``ModuleInfo.txt``), then the update/overlay
archives (their newer files replace the base's stale copies). A source that
carries nothing for the mod contributes 0 files and is reported as such.

Then we repack ONLY the mod's folder into a standalone .zip whose root is the
mod itself (ModuleInfo.txt at the top level, no wrapper folder). Packing is
always the same and deterministic: fixed compression level, sorted entries,
one fixed timestamp, fixed file mode and zip metadata. Same sources + same
arguments => byte-identical exhibit .zip every time.

Besides the exhibit .zip we write a .manifest.json with per-file hashes, the
SHA-256 of the final archive, and one entry per source (no separate .sha256
file — the archive hash lives in the manifest).

Usage
-----
    python extract_exhibit.py --exhibit ExpPilotBridge \
        --source '{"kind":"exe","path":"Space_Rangers_Universe_13.03.25.exe","mod_dir":"Mods/Expansion/ExpPilotBridge"}' \
        --source '{"kind":"zip","path":"Space Rangers Universe - Update.zip","mod_dir":"Mods/Expansion/ExpPilotBridge"}' \
        --out-dir ../../ExpPilotBridge

    # a duplicate edition: the archive carries the published id, the manifest the mod's own
    python extract_exhibit.py --exhibit ExpRC --archive-name redux__ExpRC --source '...' --out-dir ../../redux__ExpRC

    # optionally pin a source so a wrong archive fails loudly:
    --source '{"kind":"zip","path":"x.zip","mod_dir":"Mods/x","sha256":"42a7..."}'
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
TOOL_VERSION = "0.5.0"

# Fixed values so the same input always yields the same exhibit zip.
EXHIBIT_TIMESTAMP = (1980, 1, 1, 0, 0, 0)  # single normalized mtime for all entries
COMPRESS_LEVEL = 6

TOOLS_DIR = Path(__file__).resolve().parent
# The unpacker binaries the user keeps next to the museum tree
# (museum/innoextract/innoextract.exe, museum/innounp-2/innounp.exe); fall back to PATH.
MUSEUM_INNOEXTRACT = TOOLS_DIR.parent.parent / "innoextract" / "innoextract.exe"
MUSEUM_INNOUNP = TOOLS_DIR.parent.parent / "innounp-2" / "innounp.exe"


def sha256_of(path: Path) -> str:
    """SHA-256 of a file, read in chunks so it works for large archives."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def find_innoextract() -> str:
    """Return the innoextract executable path (museum-local, else on PATH), or "" if absent.

    innoextract covers Inno Setup only up to ~6.2, while newer packs (the REDUX one is Inno
    6.4.3) need innounp — so a missing binary is not fatal on its own, see ``_extract_exe_into``.
    """
    if MUSEUM_INNOEXTRACT.exists():
        return str(MUSEUM_INNOEXTRACT)
    return shutil.which("innoextract") or ""


def find_innounp() -> str:
    """Return the innounp executable path (museum-local, else on PATH), or "" if absent."""
    if MUSEUM_INNOUNP.exists():
        return str(MUSEUM_INNOUNP)
    return shutil.which("innounp") or ""


def _extract_zip_into(source: Path, mod_dir: str, merge_dir: Path) -> int:
    """Copy every file under mod_dir from source zip into merge_dir (overwriting).

    A mod the archive does not carry contributes no files — that is not an error, so the
    count (possibly 0) is returned for the log.
    """
    prefix = mod_dir.rstrip("/") + "/"
    copied = 0
    with zipfile.ZipFile(source) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename.replace("\\", "/")
            if not name.startswith(prefix) or name == prefix:
                continue
            rel = name[len(prefix):]
            dst = merge_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, dst.open("wb") as out:
                shutil.copyfileobj(src, out)
            copied += 1
    return copied


def _extract_7z_into(source: Path, mod_dir: str, merge_dir: Path) -> int:
    """Copy every file under mod_dir from a .7z archive into merge_dir (overwriting).

    Used for the pack overlays: REDUX ships "Universe Redux Fixes.7z", whose content is
    applied on TOP of the unpacked pack — a later source's files overwrite the earlier
    one's, which is exactly the semantics of the ``source`` list. py7zr (declared in
    requirements.txt) reads the archive; the overlays are small, so it is unpacked into a
    temp folder and the mod subtree is copied out. A mod the overlay does not touch
    contributes no files — that is not an error.
    """
    try:
        import py7zr
    except ImportError as exc:
        raise RuntimeError(f"py7zr is required to read {source.name}: {exc}") from exc
    archive_tmp = tempfile.mkdtemp(prefix="exhibit_7z_")
    try:
        with py7zr.SevenZipFile(source) as archive:
            archive.extractall(path=archive_tmp)
        root = Path(archive_tmp) / mod_dir
        if not root.exists():
            return 0
        return _copy_tree_into(root, merge_dir)
    finally:
        shutil.rmtree(archive_tmp, ignore_errors=True)


def _copy_tree_into(root: Path, merge_dir: Path) -> int:
    """Copy every file under root into merge_dir, keeping relative paths (overwriting).

    Returns the number of files copied: a source that contributes nothing — an overlay
    archive that does not touch this mod — then shows up as ``0 file(s)`` in the log
    instead of passing silently.
    """
    copied = 0
    for p in sorted(root.rglob("*")):
        if p.is_dir():
            continue
        dst = merge_dir / p.relative_to(root)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, dst)
        copied += 1
    return copied


def _extract_exe_with_innoextract(source: Path, mod_dir: str, merge_dir: Path, innoextract: str) -> int:
    """Extract the mod subtree with innoextract (Inno Setup up to ~6.2).

    The installer stores mods under an ``app\\`` prefix, so the include filter is
    anchored at the path start: ``\\app\\<mod_dir>``. innoextract then extracts the
    whole matched subtree preserving that prefix; we strip ``app/<mod_dir>`` and
    copy the files over.
    """
    exe_tmp = tempfile.mkdtemp(prefix="exhibit_exe_")
    try:
        cmd = [
            innoextract, "-s", "-d", exe_tmp,
            "-I", "\\app\\" + mod_dir.replace("/", "\\"),
            str(source),
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                f"innoextract failed for {source}: {exc.stderr.strip() or exc}"
            )
        root = Path(exe_tmp) / "app" / mod_dir
        if not root.exists():
            raise RuntimeError(f"mod folder {mod_dir!r} not found in installer {source}")
        return _copy_tree_into(root, merge_dir)
    finally:
        shutil.rmtree(exe_tmp, ignore_errors=True)


def _extract_exe_with_innounp(source: Path, mod_dir: str, merge_dir: Path, innounp: str) -> int:
    """Extract the mod subtree with innounp (Inno Setup up to 6.7.x).

    Needed for installers newer than innoextract understands — the REDUX pack is Inno
    6.4.3. innounp keeps the setup's ``{app}`` token as a literal directory and takes the
    files to extract as a path mask below the installation root, hence
    ``{app}\\<mod_dir>\\*.*`` (a bare directory name would extract nothing).
    """
    exe_tmp = tempfile.mkdtemp(prefix="exhibit_exe_")
    try:
        mask = "{app}\\" + mod_dir.replace("/", "\\") + "\\*.*"
        cmd = [innounp, "-x", "-b", "-y", "-q", "-o", "-h", "-d" + exe_tmp, str(source), mask]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                f"innounp failed for {source}: {exc.stderr.strip() or exc}"
            )
        root = Path(exe_tmp) / "{app}" / mod_dir
        if not root.exists():
            raise RuntimeError(f"mod folder {mod_dir!r} not found in installer {source}")
        return _copy_tree_into(root, merge_dir)
    finally:
        shutil.rmtree(exe_tmp, ignore_errors=True)


def _extract_exe_into(source: Path, mod_dir: str, merge_dir: Path, unpackers: tuple[str, ...]) -> int:
    """Extract the mod subtree from an installer .exe into merge_dir (overwriting).

    Tries every available unpacker in turn: the two cover different Inno Setup ranges
    (innoextract up to ~6.2, innounp up to 6.7.x), so whichever understands the archive
    wins. Raises with both errors when none of them manages it.
    """
    errors: list[str] = []
    for unpacker in unpackers:
        if not unpacker:
            continue
        extractor = _extract_exe_with_innounp if Path(unpacker).name.lower().startswith("innounp") else _extract_exe_with_innoextract
        try:
            return extractor(source, mod_dir, merge_dir, unpacker)
        except RuntimeError as exc:
            errors.append(str(exc))
    raise RuntimeError("; ".join(errors) or f"no unpacker available for {source}")


def _extract_source_into(kind: str, source: Path, mod_dir: str, merge_dir: Path, unpackers: tuple[str, ...]) -> int:
    """Dispatch to the extractor for one source kind; returns the number of files merged."""
    if kind == "zip":
        return _extract_zip_into(source, mod_dir, merge_dir)
    if kind == "7z":
        return _extract_7z_into(source, mod_dir, merge_dir)
    if kind == "exe":
        return _extract_exe_into(source, mod_dir, merge_dir, unpackers)
    raise RuntimeError(f"unsupported source kind {kind!r} (expected 'zip', '7z' or 'exe')")


def parse_sources(raw_sources: list[str]) -> list[tuple[str, Path, str, str | None]]:
    """Parse repeated ``--source`` JSON specs into (kind, path, mod_dir, sha256)."""
    sources: list[tuple[str, Path, str, str | None]] = []
    for raw in raw_sources:
        try:
            spec = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"invalid --source JSON: {raw} ({exc})")
        kind = (spec.get("kind") or "zip").strip().lower()
        path = (spec.get("path") or "").strip()
        mod_dir = (spec.get("mod_dir") or spec.get("target") or "").strip().rstrip("/")
        if not path or not mod_dir:
            raise RuntimeError("each --source needs 'path' and 'mod_dir'")
        sources.append((kind, Path(path), mod_dir, spec.get("sha256")))
    return sources


def build_exhibit(
    exhibit: str,
    archive_name: str,
    sources: list[tuple[str, Path, str, str | None]],
    out_dir: Path,
) -> dict:
    """Merge mod_dir from every source (later overwrites earlier) and repack flat.

    ``exhibit`` names the mod and its manifest (``<exhibit>.manifest.json``); ``archive_name``
    names the release archive (``<archive_name>.zip``). They differ for a duplicate edition:
    the REDUX exhibit of a mod that also exists in UNI is published as ``redux__<id>`` so the
    download is recognisable, while the manifest and the YAML keep the mod's own name.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    out_zip = out_dir / f"{archive_name}.zip"

    merge_dir = Path(tempfile.mkdtemp(prefix="exhibit_merge_"))
    source_info: list[dict] = []
    unpackers: tuple[str, ...] = ()
    try:
        for kind, source, mod_dir, expected_sha in sources:
            if not source.exists():
                raise RuntimeError(f"source not found: {source}")
            # Optional sanity check that we are reading the expected source.
            source_sha = sha256_of(source)
            if expected_sha and source_sha != expected_sha:
                raise RuntimeError(
                    f"source SHA-256 mismatch for {source}:\n"
                    f"  got      {source_sha}\n"
                    f"  expected {expected_sha}"
                )
            source_info.append(
                {
                    "kind": kind,
                    "archive": source.name,
                    "path": str(source),
                    "size": source.stat().st_size,
                    "sha256": source_sha,
                }
            )
            if kind == "exe" and not unpackers:
                unpackers = (find_innoextract(), find_innounp())
                if not any(unpackers):
                    raise RuntimeError(
                        "no Inno Setup unpacker found; expected "
                        f"{MUSEUM_INNOEXTRACT} or {MUSEUM_INNOUNP} (or on PATH)"
                    )
            copied = _extract_source_into(kind, source, mod_dir, merge_dir, unpackers)
            source_info[-1]["files"] = copied
            print(f"  source {source.name} ({kind}) -> {copied} file(s)")

        # The merged tree is now complete — gather the files, sorted.
        entries = [
            (p.relative_to(merge_dir).as_posix(), p)
            for p in sorted(merge_dir.rglob("*"))
            if p.is_file()
        ]
        entries.sort(key=lambda pair: pair[0])
        if not entries:
            raise RuntimeError(f"no files extracted for {exhibit}")

        # Write the deterministic exhibit zip from the merged tree.
        file_sizes: dict[str, int] = {}
        file_hashes: dict[str, str] = {}
        with zipfile.ZipFile(
            out_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=COMPRESS_LEVEL
        ) as zf:
            for out_name, src_path in entries:
                zinfo = zipfile.ZipInfo(filename=out_name, date_time=EXHIBIT_TIMESTAMP)
                zinfo.compress_type = zipfile.ZIP_DEFLATED
                zinfo.external_attr = 0o644 << 16  # fixed unix file mode
                zinfo.create_system = 3            # normalize cross-OS zip metadata
                with zf.open(zinfo, "w") as dst:
                    h = hashlib.sha256()
                    with src_path.open("rb") as src:
                        for chunk in iter(lambda: src.read(1 << 20), b""):
                            h.update(chunk)
                            dst.write(chunk)
                    file_hashes[out_name] = h.hexdigest()
                file_sizes[out_name] = src_path.stat().st_size
    finally:
        shutil.rmtree(merge_dir, ignore_errors=True)

    # Write the manifest (per-source info + archive hash + per-file hashes).
    archive_sha = sha256_of(out_zip)
    manifest = {
        "exhibit_name": exhibit,
        "source": source_info,
        "exhibit_archive": {
            "path": out_zip.name,
            "size": out_zip.stat().st_size,
            "sha256": archive_sha,
            "entries": len(entries),
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
    parser.add_argument("--exhibit", required=True, help="exhibit / mod id — names the manifest (and the exhibit in the manifest)")
    parser.add_argument("--archive-name", help="name of the release archive (default: the exhibit id); differs only for a duplicate edition, e.g. redux__ExpRC")
    parser.add_argument(
        "--source",
        action="append",
        required=True,
        metavar="JSON",
        help='source spec: {"kind":"zip|exe","path":"...","mod_dir":"...","sha256":"..."} — repeat; later sources overwrite earlier',
    )
    parser.add_argument("--out-dir", required=True, help="directory for the exhibit archive + hashes")
    args = parser.parse_args()

    try:
        sources = parse_sources(args.source)
        archive_name = (args.archive_name or args.exhibit).strip() or args.exhibit
        manifest = build_exhibit(args.exhibit, archive_name, sources, Path(args.out_dir))
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
