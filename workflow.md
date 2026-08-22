# Exhibit publish workflow

End-to-end publish chain for shipping a mod to the `space-rangers-mods-museum` museum. One run = one
exhibit; each step starts only after the previous one completes.

## Full chain — one command

| input                                                   | command                                                   | output                                                                                                       |
|---------------------------------------------------------|-----------------------------------------------------------|--------------------------------------------------------------------------------------------------------------|
| filled `exhibits/<exhibit>.yaml` (`source` + `acquire`) | `python tools/publish_exhibit.py exhibits/<exhibit>.yaml` | exhibit repo `space-rangers-mods-museum/<exhibit>` created + pushed; release `v1.0.0` (title = exhibit name) |

## Step by step

Steps are ordered **safe-first, side-effects last**: every locally executable step (extract → card →
repo folder → local git repo → showcase update) comes before anything that touches the remote org
(`gh` publish, the showcase push). Steps 1–6 run entirely on the local machine, all driven by the
orchestrator's single call and verified with `--no-publish`; steps 7–8 are the side-effects that
ship to GitHub.

`<out-dir>` defaults to the flat museum folder `museum/<exhibit>` — a sibling of `.github`, never
nested inside the showcase repo.

| step                          | phase     | input                                                          | command                                                                                                                                                             | output                                                                         |
|-------------------------------|-----------|----------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------|
| 1. Input — exhibit YAML       | safe      | manual excavation (link chains, Discord channels, dates)       | *(manual)* copy `template/exhibit-input.yaml` → fill `exhibits/<exhibit>.yaml`                                                                                          | YAML with `source` + `acquire`                                                 |
| 2. Extract & repack           | safe      | `source.path` (local file / google-disk link) + `source.target`| `python tools/extract_exhibit.py --exhibit <exhibit> --mod-dir <source.target> --source <source.path> --out-dir <out-dir>`                                          | `<exhibit>.zip`, `<exhibit>.manifest.json` (archive hash + per-file hashes)   |
| 3. Card                       | safe      | YAML + `.manifest.json` + `.zip`                               | `python tools/generate_card.py --yaml exhibits/<exhibit>.yaml --manifest <out-dir>/<exhibit>.manifest.json --zip <out-dir>/<exhibit>.zip --out <out-dir>/README.md` | `README.md` (acquire route + author + descriptions + hashes)                  |
| 4. Local repository           | safe      | artifacts of steps 2–3                                        | `python tools/publish_exhibit.py exhibits/<exhibit>.yaml --no-publish` (runs steps 2–6)                                                                              | repo folder `<out-dir>`: `README.md`, `<exhibit>.yaml`, `<exhibit>.manifest.json`, `.gitignore` |
| 5. Local git repository       | safe      | repo folder (step 4)                                          | `git -C <out-dir> init` + `git -C <out-dir> add -A` + `git -C <out-dir> commit -m "Add <exhibit>"` (done by the orchestrator in the same `--no-publish` run) | local git repo at `<out-dir>` with the initial commit — no remote yet          |
| 6. Showcase — local update    | safe      | exhibit id                                                    | `python tools/update_showcase.py --exhibit <exhibit>` (called by the orchestrator as the `showcase-local` step)                                                       | `.csv` row + main page rebuilt in `museum/.github` (local, not yet pushed)     |
| 7. Publish exhibit repo via gh| side-effect | `<out-dir>` folder                                          | `gh repo create space-rangers-mods-museum/<exhibit> --public --source <out-dir> --push` then `gh release create v1.0.0 --title "<exhibit>" <out-dir>/<exhibit>.zip` | exhibit repo `space-rangers-mods-museum/<exhibit>` live; `.zip` uploaded as release asset, then removed locally |
| 8. Showcase — commit & push   | side-effect | updated `museum/.github` (step 6)                            | `git add/commit/push` in `museum/.github` (done by the orchestrator after step 7 as `showcase-add`/`showcase-commit`/`showcase-push`)                                   | showcase repo `space-rangers-mods-museum/.github` live                        |

```
YAML → (safe, local: extract → card → repo folder → git init → showcase update) → (side-effects: publish via gh → showcase push)
```

Phase note: step 5 initializes the local git repo with the initial commit so `gh repo create
--source --push` (step 7) has something to push. Step 6 writes the showcase row whose
`mod_museum_repo_link` points at the exhibit repo — that repo does not exist until step 7. That is
fine locally; only commit & push the showcase (step 8) after step 7 has succeeded, so the pushed page
never links to a missing repo.

Three GitHub entities in the museum — do not conflate them:

- **Organization:** `space-rangers-mods-museum` — the museum itself; it hosts every exhibit repo and
  the showcase.
- **Exhibit repository:** `space-rangers-mods-museum/<exhibit>` — one repo per mod (e.g.
  `space-rangers-mods-museum/LEOGraphicsMod`); created by this workflow (step 7).
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

## Orchestrator — one command

`tools/publish_exhibit.py <exhibit.yaml>` is the driver for the whole chain: it reads the YAML and
runs extract → card → repo folder → local git init → showcase local update → `gh` publish →
showcase commit & push in order, writes a per-step log and stops on the failed step. Manual input is
limited to filling in the YAML.

```
python tools/publish_exhibit.py exhibits/LEOGraphicsMod.yaml
```

`--no-publish` stops after the safe local steps (2–6, up to and including the local showcase update)
— no `gh`, no remote — which is how the safe-first flow verifies everything locally before shipping.
Without it the orchestrator continues to the side-effect steps 7–8 (`gh` publish, then the showcase
commit & push).

## 2. Extract and repack

`tools/extract_exhibit.py` deterministically extracts the mod folder from `source` and repacks it
into a clean archive with `ModuleInfo.txt` at its root.

Artifacts: `<exhibit>.zip`, `<exhibit>.manifest.json` — the manifest carries both the SHA-256 of the
final archive and the per-file hashes (there is no separate `.sha256` file).

## 3. Card

`generate_card.py` fills the card template `template/exhibit-card.md` (the single source of the card
structure) with values from `acquire` — reproduced 1:1 as it appears in the input YAML (the
`acquire:` key and its block, wrapped in a ```yaml fenced code block, so empty `date:` fields and
key order are preserved) — plus the author and the descriptions from `ModuleInfo.txt`, and the
hashes from `.manifest.json`. The short description (from
`SmallDescriptionEng` falling back to `SmallDescription`) is rendered in the `Summary` block inside
`## 📝 Exhibit`; the detailed one (from `FullDescriptionEng` falling back to `FullDescription`) is
rendered in the separate `## 📖 Description` section. Blank or markup-only values (e.g.
`<clr><clrEnd>`) count as absent and trigger the fallback, SRHD tags are stripped for display. No
placeholder is emitted — an absent description leaves its section empty.

## 4. Local repository

The folder = the mod id: `README.md`, `<exhibit>.yaml`, `<exhibit>.manifest.json`, `.gitignore`.
The card, a copy of the exhibit YAML (it records where the instance came from), the manifest and a
generated `.gitignore` (excludes `*.zip` and `*.log`) are written by the tools into `--out-dir`
(the repo folder). The archive is **not** part of it: it ships as a release asset, kept out of the
git repo. Assembled by the orchestrator (see above):

```
python tools/publish_exhibit.py exhibits/<exhibit>.yaml --out-dir <out-dir> --no-publish
```

`--no-publish` stops after the safe local steps (2–6, incl. the local showcase update) — no `gh`,
no remote; handy for local verification before publishing.

## 5. Local git repository

Safe, local step: the orchestrator turns the finished repo folder (step 4) into a git repo and makes
the initial commit. This is what `gh repo create --source --push` (step 7) pushes — a plain folder
cannot be pushed, it must be a git repo with at least one commit. The generated `.gitignore` keeps
the archive and the log out of the commit.

```
git -C <out-dir> init
git -C <out-dir> add -A
git -C <out-dir> commit -m "Add <exhibit> exhibit"
```

Run by the orchestrator in the same `--no-publish` invocation that built the folder (steps 4–6 are
one command), so a `--no-publish` run ends with a committed local repo — no remote yet.

## 6. Showcase — local update

Safe, local step: updates the **showcase repository** `space-rangers-mods-museum/.github` (local
copy `museum/.github`) without pushing. `tools/update_showcase.py` appends the exhibit to the museum
mod list `.csv` and rebuilds the showcase main page from that `.csv` — both files in `museum/.github`
stay local until step 8. It is driven by the orchestrator (`showcase-local` step), or can be run
directly on its own.

```
python tools/update_showcase.py --exhibit <exhibit> [--name "<mod name>"]
```

`exhibits.csv` sits empty — header only:

```
mod_name,mod_author,mod_museum_repo_name,mod_museum_repo_link,mod_summary
```

Each run writes one row (mod name, author, museum repo name, repo link, summary). `mod_author` and
`mod_summary` are read from the exhibit's generated card `README.md` (the single source of those
values, in turn built from `ModuleInfo.txt`) — never asked on the command line. If the repo name is
already in the `.csv` the row is not duplicated; the tool only fills in gaps (including a missing
author/summary), so it is safe to run repeatedly. The first run writes the first row. The showcase
main page `README.md` is generated from this `.csv` (layout from `template/showcase-readme.md`) and
is never hand-edited.

## 7. Publish via gh

Side-effect step: once the local git repo (step 5) is ready — create the **exhibit repository**
(pushes `README.md`, `<exhibit>.yaml`, `<exhibit>.manifest.json`, `.gitignore`; the `.zip` is
excluded) and ship the final archive as a release asset.

```
gh repo create space-rangers-mods-museum/<exhibit> --public --source <out-dir> --push
gh release create v1.0.0 --title "<exhibit>" <out-dir>/<exhibit>.zip
```

`<out-dir>` is the local git repo built in steps 4–5. The release version is always `v1.0.0`; title —
the exhibit name (`exhibit`). After a successful release the local `<out-dir>/<exhibit>.zip` is
removed — the archive now lives only as the GitHub release asset.

## 8. Showcase — commit & push

Side-effect step: push the showcase changes produced locally in step 6. In `museum/.github` commit
and push the updated `exhibits.csv` and `README.md`. It is the final orchestrator step
(`showcase-add`/`showcase-commit`/`showcase-push`), run right after the `gh` publish.

```
git add exhibits.csv README.md
git commit -m "showcase: add <exhibit>"
git push
```

The orchestrator only runs it after step 7 has succeeded — the pushed main page links to the exhibit
repo, which does not exist until the `gh` publish completes.
