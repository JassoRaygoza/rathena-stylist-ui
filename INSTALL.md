# Stylist UI: installation

Reference base: rAthena Renewal `e985006171d2eb320ee512a653f4c83aea3d81b6`.
The diff is checked against this revision. Merge conflicts must be reviewed on other
revisions or customized servers; compatibility with other custom patches is not asserted.

## 1. Apply the server patch

Back up your source tree, configuration, character database and client files. From the
rAthena root, with your own changes saved:

```sh
git apply --check "/path/to/Stylist UI Update/diff/stylist_ui.diff"
git apply "/path/to/Stylist UI Update/diff/stylist_ui.diff"
```

The diff contains all 39 affected files, including the eight new files mirrored in
`server/`. Applying the diff is sufficient; do not subsequently overwrite your server
with those mirrors. The diff excludes local connection settings, credentials and
machine-specific compiler PDB changes.

The new source files are `src/map/stylist.cpp` and `src/map/stylist.hpp`.
Char-server transaction processing is integrated into `src/char/char_mapif.cpp`.
Visual Studio projects register the module; CMake and Make discover the map source.
The char Makefile also tracks the shared header for incremental rebuilds.

Set the matching packet version in `src/custom/defines_pre.hpp`:

```cpp
#define PACKETVER 20260219
```

This environment-specific definition is deliberately configured manually. Use the same
PACKETVER, item layout and MAX_INVENTORY when building both servers.

If `db/import/stylist_modern.yml` is missing, copy
`db/import-tmpl/stylist_modern.yml` there. Preserve and review any existing overrides.

## 2. SQL and server builds

Stop map-server and char-server before the migration/deployment. Run
`sql-files/upgrades/stylist_accessories.sql` on your **character database**, adjusting
table names first if they are customized in `conf/inter_athena.conf`.
The migration converts `char`, `inventory`, `mail` and `mail_attachments` to InnoDB
and creates the `stylist_purchase` journal. ALTER TABLE performs implicit commits.

Rebuild map-server and char-server from the patched tree using your normal rAthena
build method. Source verification used Visual Studio 18, Release x64. The existing
Linux build files are included, but this package does not claim a Linux build run.

Accessories are enabled in the package, so complete the SQL migration before players
use the service. No database migration is executed by the client patcher.

## 3. Configuration and NPC

`conf/battle_athena.conf` loads `conf/battle/stylist.conf` after the client settings
and before `conf/import/battle_conf.txt`. Review any later overrides.

```ini
feature.stylist: on
stylist_min_group: 0
stylist_class_lineage: on
stylist_costume_jobs: 30
stylist_accessory_mail: on
stylist_packet_debug: off
max_hair_style: 42
max_hair_color: 5
max_cloth_color: 667
```

The diff enables `npc/custom/stylist_modern.txt` at **Prontera 170,180** through
`npc/scripts_custom.conf`. Keep the older `npc/custom/stylist.txt` disabled at that
location. Existing merchant Stylist entry points also use the updated opening check.

`stylist_costume_jobs` adds permission bits: 1 = all eligible jobs; 2 = second;
4 = transcendent; 8 = third; 16 = fourth. The default 30 includes second through
fourth. This does not create missing catalogue rows; Novice and Baby jobs remain
ineligible. Outfit changes never change the character's actual job.

Keep `save_clothcolor: yes` and `save_body_style: yes` in the effective battle
configuration if purchased colors/outfits should persist. Set `stylist_min_group: 99`
for a restricted rollout and return it to 0 when ready.

## 4. Client files and patcher

Close the game client. Follow [client/README.md](client/README.md):

1. Import `client/data` into the client GRF, keeping its `data/...` paths.
2. Run `patcher/StylistUIPatcher.exe` and choose the compatible client EXE.
   It patches the EXE and installs the two selector-box textures in the first GRF
   listed in `DATA.INI`, saving backups first.

The compiled patcher needs `DATA.INI` beside the EXE and a top-priority GRF with
format 0x300. It does **not** install the catalogue; import that file in the previous step.
The patcher validates its supported byte locations and preserves unrelated patches.
Reference input and output hashes are listed in [patcher/README.md](patcher/README.md).

Install exactly one table at
`data/luafiles514/lua files/stylingshop/stylingshopinfo.lub`:

| Server setting | Package table |
| --- | --- |
| `stylist_class_lineage: on` | `client/data` (default) |
| `stylist_class_lineage: off` | `client/alternatives/standard/data` |

The supplied YAML is paired with these tables. Reusing the older, shorter client
table produces mismatched selection indices and missing options.

## 5. Assets and prices

The shipped human catalogue supports clothing colors 1..667, hair colors 1..5 and
hairstyles 1..42. Color 0 is the default. Doram entries retain their existing costs
and restrictions; this release does not create extra Doram sprites/palettes.

Existing choices keep their configured coupon/zeny prices; generated new choices cost
100,000 zeny. Inspect `server/db/re/stylist_modern.yml` before publishing your economy.
The client table and server YAML must always be changed together.

The numeric selectors use the loaded catalogue. Compatible PAL/SPR/ACT assets must
already be installed in the game client for every enabled appearance. No full game
client is redistributed. [Custom colours and catalogues](tools/README.md#change-the-appearance-counts) explains
the three independent limits, required resources, generated files and installation.

## 6. Verification

Double-click `tools\StylistTools.exe` and use the **Check package** tab, or run:

```bat
"C:\path\to\Stylist UI Update\tools\StylistTools.exe" --verify
```

Restart the matching map/char servers and the client. Test:

- Opening from the Prontera NPC and rejection while dead or in conflicting windows.
- The first/last hairstyle and color; dye removal back to color 0.
- Single and combined purchases, insufficient funds and coupon alternatives.
- Accessories delivered through RODEX, including a combined outfit/accessory purchase.
- Reconnect persistence, job/sex changes, mounts and temporary appearances.
- Outfit tier restrictions, male/female branches and Doram non-colorable hair.
- Favorites after changing job, and retries/reconnect without duplicate accessory delivery.

The package report distinguishes automated validation from actual in-game rendering.

## 7. Troubleshooting and rollback

| Symptom | Check |
| --- | --- |
| NPC absent | `npc/scripts_custom.conf`, duplicate NPC, map-server logs |
| Access denied | Effective `stylist_min_group`, conflicting windows, map/char connection |
| Index rejected / missing choices | Matching server YAML/client table, GRF priority, battle limits |
| Missing colors or invisible outfits | Installed PAL/SPR/ACT resources and matching catalogue |
| Accessory purchase stays pending | SQL migration, InnoDB engines, map/char versions and char-server SQL errors |
| Patcher rejects EXE or GRF | Compatible bytes/PE layout, closed client, `DATA.INI`, GRF 0x300 |
| Windows reports missing `msvcr110.dll` | The reference x64 pcre8 library needs the Microsoft Visual C++ 2012 (x64) runtime; install it or place `msvcr110.dll` beside the server executables |

Before rolling back server code, stop new purchases, disable accessory delivery and
resolve pending transactions. Preserve the `stylist_purchase` journal and its operation
IDs; do not remove it while retries may still exist. Keeping the participating tables
on InnoDB is compatible with the previous code.
Restore source/configuration and matching client-table backups together, then rebuild
and restart. Restore the EXE/GRF backups made by the patcher to undo its changes.
