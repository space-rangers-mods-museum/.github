"""Build the unpacked pack used by extract_exhibit.py.

Unpacking a multi-gigabyte pack installer for every single exhibit is wasted work (and wear on the
SSD), so a pack is unpacked **in full once** into ``origin_artefact/unpacked/<pack>`` — the
installer's content with the pack's overlays written on top, as installing the pack does it. After
that ``extract_exhibit.py`` satisfies every source of that pack from the unpacked tree and never
touches an installer or an overlay archive again.

    python build_unpacked_pack.py uni        # or redux, Solyanka, …

The sources are read from ``origin_artefact/downloaded/<pack>/``: the installer (``.exe``, unpacked
with innoextract/innounp, or ``.zip``, read directly) first, then every other ``.zip``/``.7z`` in
the folder as an overlay, in name order (a later archive wins). ``.bin`` installers' slices are
installer parts, not overlays, and are ignored. The layout is the game root at the unpacked root, so
a mod is simply ``<unpacked>/<target>``; ``sources.txt`` records the SHA-256 and size of every
archive the unpacked pack was built from, which is what keeps the exhibit manifests' provenance
without re-reading them.

An unpacked pack that already exists is left alone — delete the folder to rebuild it.
"""
from __future__ import annotations

import argparse
import hashlib
import pathlib
import shutil
import subprocess
import sys
import tempfile
import zipfile

TOOLS_DIR = pathlib.Path(__file__).resolve().parent
ROOT_DIR = TOOLS_DIR.parent.parent.parent
DOWNLOADED = ROOT_DIR / "origin_artefact" / "downloaded"
UNPACKED = ROOT_DIR / "origin_artefact" / "unpacked"
INNOEXTRACT = TOOLS_DIR.parent.parent / "innoextract" / "innoextract.exe"
INNOUNP = TOOLS_DIR.parent.parent / "innounp-2" / "innounp.exe"


def sha256_of(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sources_of(pack_dir: pathlib.Path) -> tuple[pathlib.Path, list[pathlib.Path]]:
    """The installer and the overlay archives of a downloaded pack, in application order."""
    candidates = [p for p in sorted(pack_dir.iterdir())
                  if p.is_file() and p.suffix.lower() in (".exe", ".zip")]
    if not candidates:
        raise SystemExit(f"no installer (.exe/.zip) found in {pack_dir}")
    # A pack's installer is its .exe whenever it ships one; a .zip is the installer only for the
    # packs distributed as zips (Solyanka). Otherwise an update/overlay zip whose name sorts before
    # the .exe (" " < "_") would be taken as the installer and the real one would be dropped from
    # the overlays entirely (their suffix set is .zip/.7z).
    installer = next((p for p in candidates if p.suffix.lower() == ".exe"), candidates[0])
    overlays = [p for p in sorted(pack_dir.iterdir())
                if p.is_file() and p.suffix.lower() in (".zip", ".7z") and p != installer]
    return installer, overlays


def unpack_installer(installer: pathlib.Path, cache: pathlib.Path) -> None:
    """Unpack the installer in full; the install root stays in the tool's own layout for now."""
    if installer.suffix.lower() == ".zip":
        with zipfile.ZipFile(installer) as archive:
            archive.extractall(cache)
        print(f"  unpacked {installer.name} (zip)")
        return
    if INNOUNP.exists():
        cmd = [str(INNOUNP), "-x", "-b", "-y", "-q", "-o", "-h", f"-d{cache}", str(installer)]
    else:
        cmd = [str(INNOEXTRACT), "-s", "-d", str(cache), str(installer)]
    print(f"  unpacking {installer.name} (this is the slow part, once per pack) …")
    result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        # The REDUX pack needs innounp (Inno 6.4.3), the UNI one is fine with innoextract: try the
        # other one before giving up.
        other = INNOEXTRACT if INNOUNP.exists() else INNOUNP
        cmd = ([str(other), "-s", "-d", str(cache), str(installer)] if other == INNOEXTRACT
               else [str(other), "-x", "-b", "-y", "-q", "-o", "-h", f"-d{cache}", str(installer)])
        result = subprocess.run(cmd, check=False, capture_output=True, text=True)
        if result.returncode != 0:
            raise SystemExit(f"unpacking failed: {result.stderr.strip() or result.stdout.strip()}")
    print(f"  unpacked {installer.name}")


def flatten(cache: pathlib.Path) -> None:
    """Lift the install root (`app` / `{app}`) up to the unpacked root."""
    for prefix in ("app", "{app}"):
        root = cache / prefix
        if not root.is_dir():
            continue
        moved = 0
        for child in sorted(root.iterdir()):
            target = cache / child.name
            if target.exists():
                print(f"  ! {prefix}/{child.name} exists at the root — left in place")
                continue
            shutil.move(str(child), str(target))
            moved += 1
        if not any(root.iterdir()):
            root.rmdir()
        print(f"  flattened {prefix}/ -> the unpacked root ({moved} entries)")


def apply_overlay(cache: pathlib.Path, overlay: pathlib.Path) -> tuple[int, int]:
    """Write an overlay's files over the unpacked pack; returns (added, overwritten)."""
    added = overwritten = 0
    if overlay.suffix.lower() == ".zip":
        with zipfile.ZipFile(overlay) as archive:
            entries = [(i.filename, archive.read(i)) for i in archive.infolist() if not i.is_dir()]
        for name, payload in entries:
            target = cache / name.replace("\\", "/")
            target.parent.mkdir(parents=True, exist_ok=True)
            overwritten += target.exists()
            added += not target.exists()
            target.write_bytes(payload)
    else:
        import py7zr

        staging = pathlib.Path(tempfile.mkdtemp(prefix="overlay_"))
        try:
            with py7zr.SevenZipFile(overlay) as archive:
                archive.extractall(path=staging)
            for source in sorted(p for p in staging.rglob("*") if p.is_file()):
                target = cache / source.relative_to(staging)
                target.parent.mkdir(parents=True, exist_ok=True)
                overwritten += target.exists()
                added += not target.exists()
                shutil.copyfile(source, target)
        finally:
            shutil.rmtree(staging, ignore_errors=True)
    return added, overwritten


def build(pack: str) -> None:
    pack_dir = DOWNLOADED / pack
    if not pack_dir.is_dir():
        raise SystemExit(f"pack folder not found: {pack_dir}")
    cache = UNPACKED / pack
    if cache.exists() and any(cache.iterdir()):
        raise SystemExit(f"unpacked pack already exists: {cache} — delete it to rebuild")

    installer, overlays = sources_of(pack_dir)
    print(f"building {cache}")
    unpack_installer(installer, cache)
    flatten(cache)
    for overlay in overlays:
        added, overwritten = apply_overlay(cache, overlay)
        print(f"  overlay {overlay.name}: {added} added, {overwritten} overwritten")

    lines = ["# archives this cache was built from: <sha256>  <size>  <name>"]
    for archive in (installer, *overlays):
        lines.append(f"{sha256_of(archive)}  {archive.stat().st_size}  {archive.name}")
    (cache / "sources.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    files = sum(1 for p in cache.rglob("*") if p.is_file())
    size = sum(p.stat().st_size for p in cache.rglob("*") if p.is_file()) / 1048576
    print(f"done: {files} files, {size:.1f} MB, sources.txt written")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("pack", nargs="?", help="pack folder name under origin_artefact/downloaded/")
    parser.add_argument("--list", action="store_true", help="list the packs that are already unpacked")
    args = parser.parse_args()
    if args.list or not args.pack:
        for folder in sorted(p for p in DOWNLOADED.iterdir() if p.is_dir()):
            built = "built" if (UNPACKED / folder.name).is_dir() else "—"
            print(f"{folder.name:<12} {built}")
        if not args.pack:
            sys.exit(0)
    build(args.pack)


if __name__ == "__main__":
    main()
