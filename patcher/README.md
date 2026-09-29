# Stylist UI Patcher

The compiled Windows application adds numeric selectors for hairstyle, clothing color
and hair color. It also fixes dye-removal selection, outfit-tab eligibility from the
loaded catalogue and favorites keyed by character/job.

## Use

1. Close the game and back up your client folder.
2. Run `StylistUIPatcher.exe` and choose **Select EXE...**.
3. Select the compatible client EXE. Patching starts immediately.

The patcher updates the EXE and installs two selector-box textures in the first GRF
listed in `DATA.INI`. Backups are created beside each modified file:
`<file>.<timestamp>.pre-stylist.bak`. Current files are left unchanged. Restore these
backups to undo the patch. Command-line use is also supported:

```bat
StylistUIPatcher.exe "C:\Ragnarok\client.exe"
```

It needs .NET Framework 4, `DATA.INI` beside the EXE and a top-priority GRF with
format 0x300. It does not install the catalogue Lua file;
follow `../client/README.md` for those.

## Supported client

Reference original SHA-256:
`9fd26fa04c46d97b9f83c0a8b03345605fe7dc2db8248e90e24eb0b0b2e39a79`

Output for that exact reference SHA-256:
`95fbd61d250d3d7481b271d7d1928b2a03e8ebc9fae68fdeb68f2f74496e5a65`

The runtime patcher checks PE structure, length and every patched site's bytes, allowing
supported original/previous Stylist states while preserving unrelated byte changes.
The Python recipe generator requires the exact original reference hash. Other client
builds need their own validated recipe; the date alone is insufficient.

Favorites use `name@job` in `savedata/LikeListInfoFile.lua`; the name portion is capped
at 17 bytes to fit the client's 23-character key storage. Previous name-only favorites
are not displayed under the new keys. Switching back to a job restores its saved list.

## Source and tests

`source/StylistUIPatcher.cs` contains the patcher. `generate_patch.py` builds the x86
recipe; `generated/manifest.json` lists the modified offsets and `payload.asm` shows
the injected assembly. `patch.bin` and `textures.bin` are embedded in the EXE.

From this directory, using Python 3.12 and the compatible reference client:

```bat
python -m pip install -r source\requirements-dev.txt
powershell -File source\build.ps1 -Client "C:\Ragnarok\Testing.original.exe"
set STYLIST_TEST_CLIENT=C:\Ragnarok\Testing.original.exe
python -m unittest discover -s source -p "test_*.py" -v
```

The build reads the native `bg_styling_color.bmp` from that client's GRFs to construct
the selector boxes. Tests use an x86 emulator and temporary EXE/GRF copies; the original
reference EXE is not modified.
