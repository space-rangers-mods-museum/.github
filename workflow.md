# Exhibit publish workflow

End-to-end publish chain for shipping a mod to the `space-rangers-mods-museum` museum. One run = one
exhibit; each step starts only after the previous one completes.

## Two ids: `exhibit` and `github_id`

An exhibit carries two ids. They differ only for mods that exist in more than one pack:

- **`exhibit`** — the mod's own id, without any prefix: the `mod_name` / `mod_museum_repo_name`
  columns of the catalog, so the editions of one mod group together.
- **`github_id`** — the id the exhibit is published under: the local repository folder, the exhibit
  archive and manifest, and the GitHub repository and release. It defaults to `exhibit`.

A mod that exists in **both UNI and REDUX** ships as two different exhibits under one name, and
GitHub has a single namespace — so the **REDUX edition takes the `redux__` prefix**
(`redux__ExpRC`, `redux__ExpScienceRanks`) and the UNI edition keeps the clean name. A REDUX-only
mod collides with nothing and keeps the clean name as well.

Which case applies is read from [`../../info/inventory.yaml`](../../info/inventory.yaml)
(`Solyanka` / `UNI` / `REDUX` sections): the prefix is needed exactly when the mod name appears in
both `UNI` and `REDUX`. Decide this **before** creating the exhibit — renaming a repository later
costs more than choosing the name right.

The exhibit **folder and GitHub repository** are named after the `github_id`; the files inside keep
the mod's own name, and only the release archive carries the published id — so a downloaded copy is
recognisable next to its UNI twin:

```
museum/redux__ExpRC/                # the folder = the repository name
├── ExpRC.yaml                      # exhibit: ExpRC · github_id: redux__ExpRC
├── ExpRC.manifest.json             # names the release archive (redux__ExpRC.zip)
├── README.md
└── .gitignore
```

## Full chain — one command

| input                                                   | command                                                   | output                                                                                                       |
|---------------------------------------------------------|-----------------------------------------------------------|--------------------------------------------------------------------------------------------------------------|
| filled `../<github_id>/<exhibit>.yaml` (`source` + `acquire`) | `python tools/publish_exhibit.py ../<github_id>/<exhibit>.yaml` | exhibit repo `space-rangers-mods-museum/<github_id>` created + pushed; release `v1.0.0` (title = the github_id) |

## Step by step

Steps are ordered **safe-first, side-effects last**: every locally executable step (extract → card →
repo folder → local git repo → showcase update) comes before anything that touches the remote org
(`gh` publish, the showcase push). Steps 1–6 run entirely on the local machine, all driven by the
orchestrator's single call and verified with `--no-publish`; steps 7–8 are the side-effects that
ship to GitHub.

`<out-dir>` defaults to the flat museum folder `museum/<github_id>` — a sibling of `.github`, never
nested inside the showcase repo.

| step                          | phase     | input                                                          | command                                                                                                                                                             | output                                                                         |
|-------------------------------|-----------|----------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------|
| 1. Input — exhibit YAML       | safe      | manual excavation (link chains, Discord channels, dates)       | *(manual)* copy `template/exhibit-input.yaml` → fill `../<github_id>/<exhibit>.yaml`                                                                                          | YAML with `exhibit` + `github_id` + `source` + `acquire`                       |
| 2. Extract & repack           | safe      | `source` (ordered array: each entry `kind`/`path`/`target`)    | `python tools/extract_exhibit.py --exhibit <exhibit> --archive-name <github_id> --source '{"kind":"exe","path":<installer>,"target":<mod folder>}' --source '{"kind":"zip","path":<update.zip>,"target":<mod folder>}' --out-dir <out-dir>` | `<github_id>.zip`, `<exhibit>.manifest.json` (archive hash + per-file hashes)   |
| 3. Card                       | safe      | YAML + `.manifest.json` + `.zip`                               | `python tools/generate_card.py --yaml ../<github_id>/<exhibit>.yaml --manifest <out-dir>/<exhibit>.manifest.json --zip <out-dir>/<github_id>.zip --out <out-dir>/README.md` | `README.md` (acquire route + author + descriptions + hashes)                  |
| 4. Local repository           | safe      | artifacts of steps 2–3                                        | `python tools/publish_exhibit.py ../<github_id>/<exhibit>.yaml --no-publish` (runs steps 2–6)                                                                              | repo folder `<out-dir>`: `README.md`, `<exhibit>.yaml`, `<exhibit>.manifest.json`, `.gitignore` |
| 5. Local git repository       | safe      | repo folder (step 4)                                          | `git -C <out-dir> init` + `git -C <out-dir> add -A` + `git -C <out-dir> commit -m "Add <github_id> exhibit"` (done by the orchestrator in the same `--no-publish` run) | local git repo at `<out-dir>` with the initial commit — no remote yet          |
| 6. Showcase — local update    | safe      | github_id (+ the mod id)                                      | `python tools/update_showcase.py --exhibit <github_id> --mod-id <exhibit>` (called by the orchestrator as the `showcase-local` step)                                  | `.csv` row + main page rebuilt in `museum/.github` (local, not yet pushed)     |
| 7. Publish exhibit repo via gh| side-effect | `<out-dir>` folder                                          | `gh repo create space-rangers-mods-museum/<github_id> --public --source <out-dir> --push` then `gh release create v1.0.0 --title "<github_id>" <out-dir>/<github_id>.zip` | exhibit repo `space-rangers-mods-museum/<github_id>` live; `.zip` uploaded as release asset, then removed locally |
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
- **Exhibit repository:** `space-rangers-mods-museum/<github_id>` — one repo per exhibit (e.g.
  `space-rangers-mods-museum/LEOGraphicsMod`, or `space-rangers-mods-museum/redux__ExpRC` for the
  REDUX edition of a mod that also exists in UNI); created by this workflow (step 7).
- **Showcase repository:** `space-rangers-mods-museum/.github` — a single separate repo holding the
  shared tools, the `.csv` mod list and the main showcase page built from that `.csv`; its local
  working copy is `museum/.github`, where this file and the tools live.

## 1. Input — exhibit YAML

`../<github_id>/<exhibit>.yaml` is the single source of data for the pipeline: `source` feeds
`extract_exhibit.py` — an ordered array, each entry with `kind` (`zip`, `7z` or `exe`), `path` (a google
disk link that the orchestrator downloads itself, or a path to an already-present local file — then
no download, just extract) and `target` (the mod folder inside the source). `acquire` — the route
for the card (ref/note/date fields always present, values may be empty).
Template: `template/exhibit-input.yaml`, example: `../LEOGraphicsMod/LEOGraphicsMod.yaml`.

### Manual excavation → `../<github_id>/<exhibit>.yaml`

Excavation is a manual search; there is no intermediate notes artifact. The participant records the
found route straight into the YAML. For each exhibit one YAML is assembled from its route:

- `exhibit` — the mod's own id, without any prefix.
- `github_id` — the id the exhibit is published under: the repository folder, the archive and
  manifest, and the GitHub repository. The same as `exhibit`, or `redux__<exhibit>` for the REDUX
  edition of a mod that also exists in UNI (see the section at the top).
- `source` — where the files come from: an ordered array of sources, each with `kind` (`zip` archive
  or `exe` installer), `path` — a local archive (relative path resolves against this YAML) or a
  google disk link; `target` — the path to the mod folder inside the source (e.g.
  `Mods/Expansion/ExpPilotBridge`). A later source's files overwrite an earlier one's with the same
  relative path — use the installer `.exe` first (it carries `ModuleInfo.txt`), then the update
  `.zip` (its newer files replace the base's stale copies).
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
python tools/publish_exhibit.py ../LEOGraphicsMod/LEOGraphicsMod.yaml
```

`--no-publish` stops after the safe local steps (2–6, up to and including the local showcase update)
— no `gh`, no remote — which is how the safe-first flow verifies everything locally before shipping.
Without it the orchestrator continues to the side-effect steps 7–8 (`gh` publish, then the showcase
commit & push).

## 2. Extract and repack

`tools/extract_exhibit.py` merges the mod folder from every entry in the `source` array into a shared
staging area — a later source's file overwrites an earlier one with the same relative path — and
deterministically repacks the result into a clean archive with `ModuleInfo.txt` at its root. Each
source is a `zip` archive (read directly), a `.7z` archive (read with **py7zr** — the pack overlays,
e.g. `Universe Redux Fixes.7z`, which is applied on top of the unpacked pack) or a full-game
installer `.exe`. The installer is
opened by whichever unpacker understands it: **innoextract** (`museum/innoextract/`) covers Inno Setup
up to ~6.2, **innounp** (`museum/innounp-2/`) up to 6.7.x — the UNI pack needs the first, the REDUX
pack (Inno Setup 6.4.3) only the second. **No archive is opened at all once the pack is unpacked**
under `origin_artefact/unpacked/<pack>/`: that cache holds the pack with its overlays already applied,
so every source of that pack is taken from it — the installer and the overlay archives are neither
unpacked nor hashed (`python tools/build_unpack_cache.py <pack>` builds a cache once per pack).
A typical list is
the installer `.exe` first (base, has `ModuleInfo.txt`), then the update/overlay archive (its newer
files replace the base's stale copies). Every source reports how many files it contributed — `0
file(s)` means the archive does not touch this mod (e.g. the REDUX fixes carry no `ExpRC` files), and
the exhibit then equals the content of the sources that do.

Artifacts: `<github_id>.zip`, `<exhibit>.manifest.json` — the manifest carries the SHA-256 of the
final archive, the per-file hashes, and one entry per source (there is no separate `.sha256` file).

## 3. Card

`generate_card.py` fills the card template `template/exhibit-card.md` (the single source of the card
structure) with values from `acquire` — reproduced 1:1 as it appears in the input YAML (the
`acquire:` key and its block, wrapped in a ```yaml fenced code block, so empty `date:` fields and
key order are preserved) — plus the author and the descriptions from `ModuleInfo.txt`, and the
hashes from `.manifest.json`. The card's heading is the `github_id` — so the exhibit is
recognisable at a glance — while its `Name:` line carries the mod's own id. The short description (from
`SmallDescriptionEng` falling back to `SmallDescription`; several `Key=` lines of it are joined into
one message) is rendered in the `Summary` block inside
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
python tools/publish_exhibit.py ../<github_id>/<github_id>.yaml --out-dir <out-dir> --no-publish
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
python tools/update_showcase.py --exhibit <github_id> [--mod-id <exhibit>] [--name "<mod name>"]
```

`exhibits.csv` carries one row per exhibit — header plus the exhibits published so far:

```
mod_name,mod_author,mod_museum_repo_name,mod_museum_repo_link,mod_summary,mod_github_id,mod_note
```

Each run writes one row (mod name, author, the mod's own id, repo link, summary, the id it is
published under, a note). `mod_museum_repo_name` holds the mod id and `mod_github_id` the repository
id — they differ for the REDUX edition of a mod that also exists in UNI, and such a duplicate edition
is marked with `⚠️` in `mod_note`. The marker is derived from the two ids (so it cannot drift), and a
note written by hand is never overwritten — the tool only fills an empty cell. `mod_author` and
`mod_summary`
are read from the exhibit's generated card `README.md` (the single source of those values, in turn
built from `ModuleInfo.txt`) — never asked on the command line. If the repository id is already in
the `.csv` the row is not duplicated; the tool only fills in gaps (including a missing
author/summary), so it is safe to run repeatedly. The first run writes the first row. The showcase
main page `README.md` is generated from this `.csv` (layout from `template/showcase-readme.md`) and
is never hand-edited.

## 7. Publish via gh

Side-effect step: once the local git repo (step 5) is ready — create the **exhibit repository**
(pushes `README.md`, `<exhibit>.yaml`, `<exhibit>.manifest.json`, `.gitignore`; the `.zip` is
excluded) and ship the final archive as a release asset.

```
gh repo create space-rangers-mods-museum/<github_id> --public --source <out-dir> --push
gh release create v1.0.0 --title "<github_id>" <out-dir>/<github_id>.zip
```

`<out-dir>` is the local git repo built in steps 4–5. The release version is always `v1.0.0`; title —
the `github_id`. After a successful release the local `<out-dir>/<github_id>.zip` is
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
