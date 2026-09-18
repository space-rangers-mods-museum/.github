# <img src="https://raw.githubusercontent.com/space-rangers-mods-museum/.github/main/museum.png" width="200" alt="space-rangers-mods-museum"> space-rangers-mods-museum

Historical archive of 'Space Rangers' mods. Preserved in their initial state for cultural and development history.

Updated and modified versions can be found in [space-rangers-mods-workshop](https://github.com/space-rangers-mods-workshop/.github).

## 🏛️ Why this museum exists

- **Preserve the history.** Space Rangers is a decades-old game with a rich community of mods. Many of these mods live only on dead links, vanished forums, or unlisted archives. This museum is a stable, public archive so the work of the modding community is not lost to time.
- **Keep a single, reproducible source.** Every exhibit is preserved in its initial state — an exact byte-for-byte snapshot of how it was distributed — together with a record of where it came from and how it was acquired.
- **Separate preservation from modification.** The museum holds *original* versions only. Reworked and updated releases belong to the [workshop](https://github.com/space-rangers-mods-workshop/.github), keeping the museum pure as a historical reference.

## 📦 How an exhibit is packed

Every exhibit is processed through the same deterministic pipeline, so any two runs of the tooling produce an identical result:

- The mod's files are unpacked from their source archive and repacked into a single exhibit archive, keyed by content (SHA-256) rather than file dates.
- A manifest and a generated card (`README.md`) are produced from the mod's own `ModuleInfo.txt`, so author, summary, and file listing are never hand-typed.
- The exhibit is registered in this catalog ([`exhibits.csv`](https://github.com/space-rangers-mods-museum/.github/blob/main/exhibits.csv)) and the page you are reading is rebuilt from it.

The full step-by-step workflow and tooling are documented in [workflow.md](https://github.com/space-rangers-mods-museum/.github/blob/main/workflow.md).

## 📚 Exhibit catalog

| Mod | Author | Exhibit | Note | Summary |
|-----|--------|---------|------|---------|
| AMod_MapMarker | Huk | [AMod_MapMarker](https://github.com/space-rangers-mods-museum/AMod_MapMarker) | 🥣 solyanka | Добавляет возможность ставить метку на систему галакарты |
| AMod_Spacejunk | Huk | [AMod_Spacejunk](https://github.com/space-rangers-mods-museum/AMod_Spacejunk) | 🥣 solyanka | На форме космоса добавляется панелька-смотрелка, показывающая какой предмет и где лежит в системе |
| DenButtonsPack | denball | [DenButtonsPack](https://github.com/space-rangers-mods-museum/DenButtonsPack) | 🛰️ redux | Safe to use Adds button graphics that can be used in other mods |
| DenSettingsControl | denball | [DenSettingsControl](https://github.com/space-rangers-mods-museum/DenSettingsControl) | 🛰️ redux | Safe to use Adds a panel for editing settings of game |
| ExpPilotBridge | Huk, 100kg, Klaxons | [ExpPilotBridge__uni](https://github.com/space-rangers-mods-museum/ExpPilotBridge__uni) | ⚠️ 🪐 uni | Добавляет функциональный капитанский мостик всем кораблям в игре |
| ExpRC | Huk, Klaxons | [ExpRC__redux](https://github.com/space-rangers-mods-museum/ExpRC__redux) | ⚠️ 🛰️ redux | Warning! Untranslated staff! Expands the capabilities of Ranger Centers |
| ExpScienceRanks | Huk, 100kg, uhanich, Catarsys, Klaxons | [ExpScienceRanks__uni](https://github.com/space-rangers-mods-museum/ExpScienceRanks__uni) | ⚠️ 🪐 uni | Adds the ability to gain science titles and the unique Tick hull |
| ExpSkills | Huk | [ExpSkills__redux](https://github.com/space-rangers-mods-museum/ExpSkills__redux) | ⚠️ 🛰️ redux | Warning! Untranslated staff! Extra skills |
| LEOGraphicsMod | LEOPARD | [LEOGraphicsMod](https://github.com/space-rangers-mods-museum/LEOGraphicsMod) | 🥣 solyanka | Содержит в себе всю графику и звук из "Солянки" и "AnotherMods" |
| UtilityFunctionsPack | Klaxons, denball | [UtilityFunctionsPack__uni](https://github.com/space-rangers-mods-museum/UtilityFunctionsPack__uni) | ⚠️ 🪐 uni | Adds a set of useful modding features |
