# Tools

## Stylist Tools (no Python needed)

**Double-click `StylistTools.exe`.** It runs on any Windows 10/11 PC (it uses .NET Framework 4,
which Windows already includes), so nothing has to be installed. The window has three tabs:

| Tab | What it does |
| --- | --- |
| **1. Appearance counts** | Choose how many clothing colors (BodyColor), hair colors (HairColor) and hairstyles (HairStyle) players can pick, then click **Generate files**. |
| **2. Patch the client** | Opens `patcher\StylistUIPatcher.exe`, which adds the numeric selectors to your game client. |
| **Check package** | Confirms that no file of this package is missing or was changed. Package authors also create `SHA256SUMS.txt` here. |

### Change the appearance counts

1. Type the three numbers. Each number is the highest ID offered; color 0 (the original
   color) is always included in addition. **Use package values** restores 667 / 5 / 42 and
   **Load from a .conf file...** reads the `max_*` values from an rAthena configuration file.
2. Leave the suggested result folder or choose another **new, empty** folder.
3. Click **Generate files**. When it finishes, click **Open install steps** and follow them:
   copy the server catalogue and limits to your server and the client table to your GRF.

Your client must already have the sprites/palettes (PAL/SPR/ACT) for every ID you enable; the tool
only creates the matching catalogue and configuration files. Existing installed files are never
modified.

**Show advanced options** gives access to:

- **Price of new entries**: zeny price of newly added choices (existing choices keep their prices).
- **Also extend Doram options**: only if your client has the Doram resources for the whole range.
- **rAthena folder**: optional. The tool already contains the job and item data of the tested
  rAthena base. Select your patched rAthena folder (the one containing `src` and `db`) only if you
  changed jobs, lineages or item names. `STYLIST_SERVER_ROOT`, when set, is used automatically.
- **Custom source table**: an edited copy of `client/source/stylingshopinfo.lub`.

### Command line

The same EXE also works from a command prompt, for scripts:

```bat
tools\StylistTools.exe --cloth-colors 700 --hair-colors 12 --hairstyles 50 --output generated\my-stylist
tools\StylistTools.exe --from-conf my-stylist.conf --hair-colors 8 --output generated\other
tools\StylistTools.exe --verify
tools\StylistTools.exe --write-checksums
tools\StylistTools.exe --help
```

Other options: `--include-doram`, `--new-entry-price N`, `--source FILE` and `--server FOLDER`.
With only `--output` it asks for the three counts in the console. It returns exit code 0 on
success and 1 on failure.

## Check this package

Open the **Check package** tab and click **Check package files**, or run
`tools\StylistTools.exe --verify`. It verifies `SHA256SUMS.txt` and checks the new server files
against the complete diff. It does not modify a server, game client or database.

### Create SHA256SUMS.txt (package authors)

When the package is finished, click **Create SHA256SUMS.txt** in the same tab, or run
`tools\StylistTools.exe --write-checksums`. It records the hash of every file in the package and
then runs the check above. Files that `.gitignore` excludes are skipped: the root `generated`
folder, `__pycache__`, `.venv`, `*.pyc` and `*.bak` backups. Create it again after any later
change, including a rebuild of `StylistTools.exe`; an existing file is replaced (the window asks
first).

## For developers

`catalogue/` keeps the original Python generator (`configure_catalogue.py`,
`generate_catalogue.py`) and its tests. `StylistTools.exe` is a C# port that produces
byte-identical files; `verify_package.py` is the Python equivalent of `--verify`.

### Rebuild and test

`source/` contains the C# code (`Program.cs`, `MainForm.cs`, `Catalogue.cs`, `Verify.cs`) and
`reference.txt`, the built-in job constants and item names exported from the patched rAthena tree.
Build with the compiler included in Windows:

```powershell
powershell -File tools\source\build.ps1
# Refresh reference.txt when jobs, lineages or items change on the server:
powershell -File tools\source\build.ps1 -Server C:\rAthena
```

The build also embeds `server/src/map/stylist.hpp`, `client/source/stylingshopinfo.lub` and
`server/conf/battle/stylist.conf`, so rebuild after changing any of them.

With Python 3.12 and `STYLIST_SERVER_ROOT` set to the patched source tree, run the catalogue tests
and the EXE-versus-Python comparison:

```sh
python -m unittest discover -s tools/catalogue -p "test_*.py" -v
python -m unittest discover -s tools/source -p "test_*.py" -v
```
