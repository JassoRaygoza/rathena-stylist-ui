# rAthena Stylist UI

Modern native **Stylist** integration for [rAthena](https://github.com/rathena/rathena)
Renewal, with a complete server DIFF, matching client tables and a Windows client EXE
patcher. The new module is contained in **stylist.cpp** and **stylist.hpp**.

[Installation](INSTALL.md) | [BodyColor / HairStyle / HairColor guide](tools/README.md#change-the-appearance-counts) | [Patcher](patcher/README.md)

> **Palettes download (GRF):** https://drive.google.com/file/d/10zQj1eJj0blOS9pyyiopvrdMsFTssn7p/view?usp=sharing

> **No Python needed.** Double-click [tools/StylistTools.exe](tools/StylistTools.exe) to choose the
> appearance counts, open the client patcher or check the package, all from one window.

## Features

- Numeric selectors for BodyColor, HairStyle and HairColor, using the loaded client catalogue.
- Outfits from the character's evolution branch, while preserving the actual job.
- Outfit eligibility by job tier, sex and catalogue, rechecked on login, job/sex changes and configuration reloads.
- Aggregate validation of purchases paid with zeny or alternative coupons.
- Accessories delivered through RODEX, with a durable SQL purchase journal and retry handling.
- Client fixes for dye removal, outfit-tab eligibility and favorites per character/job.
- Central configuration in [stylist.conf](server/conf/battle/stylist.conf).

## Guides

| Task | Direct guide |
| --- | --- |
| Install the complete system | [Installation, SQL migration, builds and deployment](INSTALL.md) |
| Change BodyColor, HairStyle or HairColor quantities | [Settings, limits and required resources](tools/README.md#change-the-appearance-counts) |
| Generate your own matching files | Double-click [StylistTools.exe](tools/README.md#stylist-tools-no-python-needed), or use its [command line](tools/README.md#command-line) |
| Install newly generated counts | **Open install steps** after generating, or `INSTALL.md` inside the generated folder |
| Patch the client EXE | [Patcher usage and supported client](patcher/README.md) |
| Choose and install the client table | [Client files](client/README.md) |
| Verify the package files | **Check package** tab in [StylistTools.exe](tools/README.md#check-this-package) |

## Requirements

- rAthena Renewal; tested base: `e985006171d2eb320ee512a653f4c83aea3d81b6`. See the [base and file list](diff/base.json).
- The reference **2026-02-19** client layout and `PACKETVER 20260219`. The [patcher validates its supported byte locations](patcher/README.md#supported-client); the client date alone does not establish compatibility.
- Client PAL/SPR/ACT resources for every enabled appearance ID, as explained in the [appearance guide](tools/README.md#change-the-appearance-counts).
- MySQL/MariaDB, InnoDB transaction tables and the included [accessory SQL migration](server/sql-files/upgrades/stylist_accessories.sql).
- Matching map-server and char-server builds.
- Windows with .NET Framework 4 for [StylistTools.exe](tools/StylistTools.exe) and the client patcher. It is already included in Windows 10 and 11; nothing else has to be installed.
- Python 3.12 is optional: only needed to develop or test the tools.

## Package layout

| Path | Contents |
| --- | --- |
| [diff/stylist_ui.diff](diff/stylist_ui.diff) | Complete server patch, including modified and new files. **Apply this file.** |
| [server/](server/) | The eight new server files already included in the DIFF, for browsing and review |
| [client/](client/README.md) | Expanded and standard client-table variants, plus the credited generator input |
| [patcher/StylistUIPatcher.exe](patcher/StylistUIPatcher.exe) | Compiled client patcher; [source and resources](patcher/source/) are included |
| [tools/StylistTools.exe](tools/README.md) | Appearance-count generator, patcher launcher and package check in one window; no Python required |
| [tools/catalogue/](tools/catalogue/) | Python reference generator and tests (optional, for developers) |
| `SHA256SUMS.txt` | Release file checksums; [create and check them](tools/README.md#check-this-package) with StylistTools.exe |

## Quick install

From the rAthena root:

```sh
git apply --check "/path/to/Stylist UI Update/diff/stylist_ui.diff"
git apply "/path/to/Stylist UI Update/diff/stylist_ui.diff"
```

Then follow the [full installation guide](INSTALL.md) to set `PACKETVER 20260219`,
apply the [SQL migration](server/sql-files/upgrades/stylist_accessories.sql), rebuild
map-server and char-server, install the [client table](client/data/) and run the
[EXE patcher](patcher/StylistUIPatcher.exe) (also available from the **Patch the client** tab of [StylistTools.exe](tools/StylistTools.exe)).

The DIFF already includes every new server file. The package enables the
[Stylist NPC](server/npc/custom/stylist_modern.txt) at **Prontera 170,180** for all players.

## Appearance counts

The included client tables and [server catalogue](server/db/re/stylist_modern.yml) use:

| Appearance | Setting | Included maximum ID |
| --- | --- | --- |
| BodyColor | `max_cloth_color` | 667 |
| HairStyle | `max_hair_style` | 42 |
| HairColor | `max_hair_color` | 5 |

Color 0 is the original/default color and is additional. Each quantity can be changed
independently:

1. Double-click **tools/StylistTools.exe**.
2. Type the three counts, for example **700** clothing colors, **12** hair colors and **50** hairstyles.
3. Click **Generate files**, then **Open install steps** and copy the files to your server and client.

The tool already contains the data of the tested rAthena base, so you do not need to point it at
your server source. The same result from a command prompt:

```bat
tools\StylistTools.exe --cloth-colors 700 --hairstyles 50 --hair-colors 12 --output generated\my-stylist
```

Follow the `INSTALL.md` created in the result folder to install the generated configuration,
server YAML and client table together. Changing only a server limit does not add client
choices or create the PAL/SPR/ACT resources for those IDs.

## Configuration

[conf/battle/stylist.conf](server/conf/battle/stylist.conf) is loaded by
`conf/battle_athena.conf`. Later settings in `conf/import/battle_conf.txt` take precedence.

| Setting | Package default | Purpose |
| --- | --- | --- |
| `feature.stylist` | `on` | Enables the service |
| `stylist_min_group` | `0` | All players; use 99 for a restricted rollout |
| `stylist_class_lineage` | `on` | Uses the [expanded client table](client/data/) |
| `stylist_costume_jobs` | `30` | Second, transcendent, third and fourth job tiers |
| `stylist_accessory_mail` | `on` | Durable RODEX purchases; requires the SQL migration |
| `stylist_packet_debug` | `off` | Optional action/index diagnostic logging |

For `stylist_class_lineage: off`, use the [standard client table](client/alternatives/standard/data/).
See [configuration and NPC details](INSTALL.md#3-configuration-and-npc) for the permission
mask and appearance persistence. Novice and Baby jobs cannot change outfits; Doram
retains its species and non-colorable-hairstyle restrictions.

## Validation status

The complete DIFF was applied and compared against its exact
base: all 39 resulting files matched. The server logic compiled in Visual Studio 18,
Release x64, for map-server and char-server with zero warnings and errors.

The included patcher passed 27 tests, and the catalogue generator passed 8 tests.
The appearance-count checks confirm both the shipped
667/42/5 pair and the documented 700/50/12 example.

Actual in-game rendering must still be checked with the resources installed in your
client. See the [deployment test steps](INSTALL.md#6-verification).

## Contributing

Update the DIFF and corresponding files in [server/](server/) together. Regenerate the
server YAML and client table as a pair when changing choices. Rebuild both servers
when the shared transaction layout changes, and run the [catalogue tests](tools/README.md#rebuild-and-test)
and [patcher tests](patcher/README.md#source-and-tests). After changing the generator, rebuild
[StylistTools.exe](tools/README.md#rebuild-and-test) and run its byte-for-byte comparison against the Python generator. Include the rAthena revision,
client build, PACKETVER and relevant settings in bug reports.

## Credits and license

Server code derives from rAthena and uses [GNU GPL v3](LICENSE). Original client-table
credits to zackdreaver and llchrisll / ROenglishRE remain in the Lua files. Ragnarok
Online resources retain their respective owners' rights
and terms. See [NOTICE.md](NOTICE.md).
