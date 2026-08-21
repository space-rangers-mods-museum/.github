# Exhibit publish workflow

End-to-end publish chain for shipping a mod to the `space-rangers-mods-museum` museum. One run = one
exhibit; each step starts only after the previous one completes.

## Full chain — one command

| input                                                   | command                                                   | output                                                                                                       |
|---------------------------------------------------------|-----------------------------------------------------------|--------------------------------------------------------------------------------------------------------------|
| filled `exhibits/<exhibit>.yaml` (`source` + `acquire`) | `python tools/publish_exhibit.py exhibits/<exhibit>.yaml` | exhibit repo `space-rangers-mods-museum/<exhibit>` created + pushed; release `v1.0.0` (title = exhibit name) |

## Step by step

`<out-dir>` defaults to the flat museum folder `museum/<exhibit>` — a sibling of `.github`, never
nested inside the showcase repo.

| step                        | input                                                           | command                                                                                                                                                             | output                                                                         |
|-----------------------------|-----------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------|
| 1. Input — exhibit YAML     | manual excavation (link chains, Discord channels, dates)        | *(manual)* copy `template/exhibit-input.yaml` → fill `exhibits/<exhibit>.yaml`                                                                                          | YAML with `source` + `acquire`                                                 |
| 2. Orchestrator             | `exhibits/<exhibit>.yaml`                                       | `python tools/publish_exhibit.py exhibits/<exhibit>.yaml`                                                                                                           | runs steps 3–6 in order, logs each step, stops on the failed one               |
| 3. Extract & repack         | `source.path` (local file / google-disk link) + `source.target` | `python tools/extract_exhibit.py --exhibit <exhibit> --mod-dir <source.target> --source <source.path> --out-dir <out-dir>`                                          | `<exhibit>.zip`, `<exhibit>.manifest.json` (archive hash + per-file hashes)   |
| 4. Card                     | YAML + `.manifest.json` + `.zip`                                | `python tools/generate_card.py --yaml exhibits/<exhibit>.yaml --manifest <out-dir>/<exhibit>.manifest.json --zip <out-dir>/<exhibit>.zip --out <out-dir>/README.md` | `README.md` (acquire route + author + descriptions + hashes)                  |
| 5. Local repository         | artifacts of steps 3–4                                          | *(assembled by the orchestrator)* — or locally: `python tools/publish_exhibit.py exhibits/<exhibit>.yaml --no-publish`                                              | repo folder `<out-dir>`: `README.md`, `<exhibit>.yaml`, `<exhibit>.manifest.json` |
| 6. Publish via gh           | `<out-dir>` folder                                              | `gh repo create space-rangers-mods-museum/<exhibit> --public --source <out-dir> --push` then `gh release create v1.0.0 --title "<exhibit>" <out-dir>/<exhibit>.zip` | exhibit repo `space-rangers-mods-museum/<exhibit>` live; `.zip` uploaded as release asset, then removed locally |
| 7. Showcase (separate step) | published exhibit (repo name)                                   | `python tools/update_showcase.py --exhibit <exhibit>` (runs **separately** from the orchestrator)                                                                      | `.csv` row appended + main page rebuilt in `space-rangers-mods-museum/.github` |

```
YAML → orchestrator → (extract → card → repo folder → publish via gh) → showcase
```

Three GitHub entities in the museum — do not conflate them:

- **Organization:** `space-rangers-mods-museum` — the museum itself; it hosts every exhibit repo and
  the showcase.
- **Exhibit repository:** `space-rangers-mods-museum/<exhibit>` — one repo per mod (e.g.
  `space-rangers-mods-museum/LEOGraphicsMod`); created by this workflow (step 6).
- **Showcase repository:** `space-rangers-mods-museum/.github` — a single separate repo holding the
  shared tools, the `.csv` mod list and the main showcase page built from that `.csv`; its local
  working copy is `museum/.github`, where this file and the tools live.

## 1. Input — exhibit YAML

`exhibits/<exhibit>.yaml` is the single source of data for the pipeline: `source` feeds
`extract_exhibit.py` (path — a google disk link that the orchestrator downloads itself, or a path to
an already-present local file — then no download, just extract; target — the mod folder inside the
source), `acquire` — the route for the card (ref/note/date fields always present, values may be
empty).
Template: `template/exhibit-input.yaml`, example: `exhibits/LEOGraphicsMod.yaml`.

### Manual excavation → `exhibits/<exhibit>.yaml`

Excavation is a manual search; there is no intermediate notes artifact. The participant records the
found route straight into the YAML. For each exhibit one YAML is assembled from its route:

- `exhibit` — the mod id (name of the museum repo folder).
- `source` — where the files come from: `path` — a local archive/folder (relative path resolves
  against this YAML) or a google disk link; `target` — the path to the mod folder inside the source
  (e.g. `Mods/Solyanka/LEOGraphicsMod`).
- `acquire` — each step of the chain (from the starting point to the local file) becomes a
  `ref`/`note`/`date` entry: `ref` — the step's working link, `note` — a short description
  in English (verbatim names of external resources — Discord channels, collection/mod-pack titles —
  stay in their original spelling, even if non-Latin), `date` — the post/file date if known. Fields
  are always present, but empty values are allowed.

## 2. Orchestrator — one command

`tools/publish_exhibit.py <exhibit.yaml>` reads the YAML and runs the whole chain in order
(steps 3–6), writes a per-step log to a file and stops on the failed step. Manual input is limited to
filling in the YAML.

```
python tools/publish_exhibit.py exhibits/LEOGraphicsMod.yaml
```

## 3. Extract and repack

`tools/extract_exhibit.py` deterministically extracts the mod folder from `source` and repacks it
into a clean archive with `ModuleInfo.txt` at its root.

Artifacts: `<exhibit>.zip`, `<exhibit>.manifest.json` — the manifest carries both the SHA-256 of the
final archive and the per-file hashes (there is no separate `.sha256` file).

## 4. Card

`generate_card.py` fills the card template `template/exhibit-card.md` (the single source of the card
structure) with values from `acquire` (the acquisition route), the author and the descriptions from
`ModuleInfo.txt`, and the hashes from `.manifest.json`. Descriptions: short from
`SmallDescriptionEng` (falling back to `SmallDescription`), detailed from `FullDescriptionEng`
(falling back to `FullDescription`); blank or markup-only values (e.g. `<clr><clrEnd>`) count as
absent and trigger the fallback, SRHD tags are stripped for display.

## 5. Local repository

The folder = the mod id: `README.md`, `<exhibit>.yaml`, `<exhibit>.manifest.json`. The card, a copy
of the exhibit YAML (it records where the instance came from) and the manifest are written by the
tools into `--out-dir` (the repo folder). The archive is **not** part of it: it ships as a release
asset, kept out of the git repo by a generated `.gitignore` (`*.zip`). Assembled by the orchestrator
(step 2):

```
python tools/publish_exhibit.py exhibits/<exhibit>.yaml --out-dir <out-dir> --no-publish
```

`--no-publish` stops after the finished folder (steps 3–5) — no `gh` or `git`; handy for local
verification before publishing.

## 6. Publish via gh

Once the repo folder is ready — create the **exhibit repository** (pushes `README.md`,
`<exhibit>.yaml`, `<exhibit>.manifest.json`, `.gitignore`; the `.zip` is excluded) and ship the
final archive as a release asset.

```
gh repo create space-rangers-mods-museum/<exhibit> --public --source <out-dir> --push
gh release create v1.0.0 --title "<exhibit>" <out-dir>/<exhibit>.zip
```

`<out-dir>` is the repo folder built in step 5. The release version is always `v1.0.0`; title — the
exhibit name (`exhibit`). After a successful release the local `<out-dir>/<exhibit>.zip` is removed
— the archive now lives only as the GitHub release asset.

## 7. Showcase (separate step)

Updates the **showcase repository** `space-rangers-mods-museum/.github` (local copy
`museum/.github`). `tools/update_showcase.py` runs **separately** from the main chain (not by the
orchestrator): it appends the exhibit to the museum mod list `.csv` and rebuilds the showcase main
page from that `.csv`.

```
python tools/update_showcase.py --exhibit <exhibit> [--name "<mod name>"]
```

`exhibits.csv` sits empty — header only:

```
mod_name,mod_museum_repo_name,mod_museum_repo_link
```

Each run writes one row (mod name, museum repo name, repo link); if the repo name is already in the
`.csv` the row is not duplicated, so the tool is safe to run repeatedly. The first run writes the
first row. The showcase main page `README.md` is generated from this `.csv` (layout from
`template/showcase-readme.md`) and is never hand-edited.
