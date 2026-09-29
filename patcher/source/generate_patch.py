"""Build the Stylist UI patch recipe from the reference client. Never edits the input EXE."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

import pefile
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

SOURCE_SHA256 = "9fd26fa04c46d97b9f83c0a8b03345605fe7dc2db8248e90e24eb0b0b2e39a79"
BASE = 0x4A14000
CREATE, BUTTON, LOOKUP, DISPATCH, DRAW = [BASE + n for n in (0, 0x200, 0x400, 0x600, 0x800)]
COUNT, FORMAT = BASE + 0xF00, BASE + 0xF10
SEQ_NAME, GOODS_NAME = BASE + 0xF40, BASE + 0xF80
PREVIOUS, NEXT = 0x7EF0, 0x7EF1
PREVIEW_DRAW, LABEL = BASE + 0xA00, BASE + 0xB00
STYLE_FORMAT, CLOTH_FORMAT, SIZE_NAME = BASE + 0xFA0, BASE + 0xFC0, BASE + 0xFE0
BITMAP, HAIR_BOX_PATH, STYLE_BOX_PATH = BASE + 0xC00, BASE + 0xD00, BASE + 0xD80
RESET_SENTINEL = BASE + 0xE00
COSTUME_COUNT, COSTUME_TAB, COSTUME_CLICK = BASE + 0xC40, BASE + 0xE40, BASE + 0xE60
COSTUME_TAB_ID = 0x247
FAV_NAME, FAV_BUFFER, FAV_FORMAT = BASE + 0x900, BASE + 0xEA0, BASE + 0xEE0
# Favorites (savedata/LikeListInfoFile.lua) are keyed by "name@job". The file
# reader copies the key with strcpy_s(buffer, 24), so it must stay <= 23 chars.
FAV_NAME_CHARS = 17
FAV_NAME_CALLS = (0x825F89, 0x82A503, 0x82A8AB, 0x82ABF3)
# Selector box textures installed by client_assets.py (drawn only if present).
UI_FOLDER = "유저인터페이스\\styleshop\\"
HAIR_BOX_BMP = UI_FOLDER + "bg_stylist_haircolor_box.bmp"
STYLE_BOX_BMP = UI_FOLDER + "bg_stylist_selector_box.bmp"
HAIR_BOX_POS, HAIR_BOX_SIZE = (71, 233), (174, 42)
STYLE_BOX_POS, STYLE_BOX_SIZE = (4, 24), (242, 50)
# Hair color arrows line up with the native hairstyle/clothing arrows (x=231).
HAIR_ARROW_X, HAIR_TEXT_X = (108, 231), 124


def assemble(source, address):
    return bytes(Ks(KS_ARCH_X86, KS_MODE_32).asm(source, address)[0])


def payload():
    # The native vector remains empty. UI parent ownership releases the two
    # ordinary momentary buttons; the separate native default-color button stays.
    create = f"""
        mov eax, [ebp-0xf8]
        test eax, eax
        jns count_positive
        xor eax, eax
    count_positive:
        cmp eax, 32766
        jle count_valid
        xor eax, eax
    count_valid:
        mov dword ptr [{COUNT}], eax
        push 0x112f38c
        push 0x112f358
        push {PREVIOUS}
        push {HAIR_ARROW_X[0]}
        push edi
        call {BUTTON}
        push 0x112f3f4
        push 0x112f3c0
        push {NEXT}
        push {HAIR_ARROW_X[1]}
        push edi
        call {BUTTON}
        xor esi, esi
        mov [ebp-0xf0], esi
        jmp 0x828738
    """
    button = """
        push ebp
        mov ebp, esp
        push esi
        push 0x11b5950
        push 0x120
        call 0xe624ae
        add esp, 8
        test eax, eax
        jz button_done
        mov ecx, eax
        call 0x84eab0
        mov esi, eax
        push 0
        push 0
        push dword ptr [ebp+20]
        mov ecx, esi
        call 0x8657a0
        push 0
        push 1
        push dword ptr [ebp+24]
        mov ecx, esi
        call 0x8657a0
        push 0
        push 2
        push dword ptr [ebp+24]
        mov ecx, esi
        call 0x8657a0
        push dword ptr [esi+0xb8]
        push dword ptr [esi+0xb4]
        mov ecx, esi
        call 0xa7b470
        mov eax, [esi]
        push 252
        push dword ptr [ebp+12]
        mov ecx, esi
        call dword ptr [eax+0x10]
        mov eax, [esi]
        push dword ptr [ebp+16]
        mov ecx, esi
        call dword ptr [eax+0xb4]
        push esi
        mov ecx, [ebp+8]
        call 0xa7a080
    button_done:
        pop esi
        pop ebp
        ret 20
    """
    # lookup(function C string, length, value, table, has_value): native by-value
    # std::string using the client's allocator. The Lua bridge destroys it.
    lookup = """
        push ebp
        mov ebp, esp
        sub esp, 4
        push ebx
        push esi
        push edi
        mov dword ptr [ebp-4], 0
        lea eax, [ebp-4]
        push eax
        cmp dword ptr [ebp+24], 0
        je size_query
        push dword ptr [ebp+16]
        push dword ptr [ebp+20]
        push 0x10e0eb4
        jmp query_string
    size_query:
        push dword ptr [ebp+20]
        push 0x10df0e4
    query_string:
        sub esp, 24
        mov ebx, esp
        mov dword ptr [ebx], 0
        mov dword ptr [ebx+16], 0
        mov dword ptr [ebx+20], 15
        push 48
        mov ecx, ebx
        call 0x4fa050
        mov [ebx], eax
        mov ecx, [ebp+12]
        mov [ebx+16], ecx
        mov dword ptr [ebx+20], 47
        inc ecx
        mov edi, eax
        mov esi, [ebp+8]
        cld
        rep movsb
        push dword ptr [0x1738010]
        call 0xafc9a0
        add esp, 40
        cmp dword ptr [ebp+24], 0
        je query_done
        add esp, 4
    query_done:
        mov eax, [ebp-4]
        pop edi
        pop esi
        pop ebx
        mov esp, ebp
        pop ebp
        ret 20
    """
    seq = "StylingShop_GetSeqnumber_by_goods"
    goods = "StylingShop_GetGoods"
    dispatch = f"""
        mov eax, [ebp+0x10]
        cmp eax, 0x1ef
        je default_button
        cmp eax, {PREVIOUS}
        je arrow
        cmp eax, {NEXT}
        jne 0x82d37a
    arrow:
        cmp dword ptr [{COUNT}], 0
        jle 0x82d37a
        mov eax, [edi+0x7c]
        push 1
        push 0x112f730
        push dword ptr [eax+0x94]
        push {len(seq)}
        push {SEQ_NAME}
        call {LOOKUP}
        cmp dword ptr [ebp+0x10], {PREVIOUS}
        je previous_color
        inc eax
        cmp eax, dword ptr [{COUNT}]
        jg first_color
        cmp eax, 1
        jge resolve_color
    first_color:
        mov eax, 1
        jmp resolve_color
    previous_color:
        dec eax
        cmp eax, 1
        jl last_color
        cmp eax, dword ptr [{COUNT}]
        jle resolve_color
    last_color:
        mov eax, dword ptr [{COUNT}]
    resolve_color:
        push 1
        push 0x112f730
        push eax
        push {len(goods)}
        push {GOODS_NAME}
        call {LOOKUP}
        test eax, eax
        jle 0x82d37a
        cmp eax, 32766
        jg 0x82d37a
        lea esi, [eax-1]
        mov [ebp+0x18], esi
        jmp 0x82d213
    default_button:
        mov eax, [ebp+8]
        cmp eax, [edi+0x94]
        je 0x82d34a
        jmp 0x82d37a
    """
    draw = f"""
        push ebp
        mov ebp, esp
        sub esp, 64
        push esi
        mov esi, ecx
        call 0x829c30
        push {HAIR_BOX_PATH}
        push {HAIR_BOX_POS[1]}
        push {HAIR_BOX_POS[0]}
        mov ecx, esi
        call {BITMAP}
        mov eax, [esi+0x7c]
        test eax, eax
        jz draw_done
        push 1
        push 0x112f730
        push dword ptr [eax+0x94]
        push {len(seq)}
        push {SEQ_NAME}
        call {LOOKUP}
        test eax, eax
        jns display_index
        xor eax, eax
    display_index:
        push dword ptr [{COUNT}]
        push eax
        push {FORMAT}
        push 64
        lea eax, [ebp-64]
        push eax
        call 0x602b00
        add esp, 20
        push 0
        push 0
        push 0x303030
        push 11
        push 0
        push 0
        lea eax, [ebp-64]
        push eax
        push 253
        push {HAIR_TEXT_X}
        mov ecx, esi
        call 0xa84360
    draw_done:
        pop esi
        mov esp, ebp
        pop ebp
        ret
    """
    # Reuse native hairstyle/clothing arrow handlers, including race-specific
    # catalogue resolution. Only their positions and numeric captions change.
    preview_draw = f"""
        push esi
        mov esi, ecx
        call 0x829d10
        cmp byte ptr [esi+0xb0], 0
        jne preview_done
        push {STYLE_BOX_PATH}
        push {STYLE_BOX_POS[1]}
        push {STYLE_BOX_POS[0]}
        mov ecx, esi
        call {BITMAP}
        push 32
        push {STYLE_FORMAT}
        push 0x8c
        push 2
        mov ecx, esi
        call {LABEL}
        push 54
        push {CLOTH_FORMAT}
        push 0x98
        push 3
        mov ecx, esi
        call {LABEL}
    preview_done:
        pop esi
        ret
    """
    label = f"""
        push ebp
        mov ebp, esp
        sub esp, 96
        push ebx
        push esi
        push edi
        mov esi, ecx
        lea eax, [ebp+8]
        push eax
        lea eax, [ebp-24]
        push eax
        call 0x8264a0
        mov edi, eax
        cmp dword ptr [edi+20], 16
        jb table_ready
        mov edi, [edi]
    table_ready:
        push 0
        push edi
        push 0
        push {len('StylingShop_GetSizeInTable')}
        push {SIZE_NAME}
        call {LOOKUP}
        mov ebx, eax
        mov eax, [ebp+12]
        push 1
        push edi
        push dword ptr [esi+eax]
        push {len(seq)}
        push {SEQ_NAME}
        call {LOOKUP}
        test eax, eax
        jns label_index
        xor eax, eax
    label_index:
        push ebx
        push eax
        push dword ptr [ebp+16]
        push 64
        lea eax, [ebp-88]
        push eax
        call 0x602b00
        add esp, 20
        lea ecx, [ebp-24]
        call 0x4f98a0
        push 0
        push 0
        push 0x303030
        push 12
        push 0
        push 0
        lea eax, [ebp-88]
        push eax
        push dword ptr [ebp+20]
        push 48
        mov ecx, esi
        call 0xa84360
        pop edi
        pop esi
        pop ebx
        mov esp, ebp
        pop ebp
        ret 16
    """
    # bitmap(x, y, texture path): native resource lookup and blit; skipped if missing.
    bitmap = """
        push ebp
        mov ebp, esp
        push esi
        push edi
        mov edi, ecx
        call 0xaf1620
        mov esi, eax
        push dword ptr [ebp+16]
        call 0xb01200
        add esp, 4
        push eax
        mov ecx, esi
        call 0xaee770
        test eax, eax
        jz bitmap_done
        push 0
        push eax
        push dword ptr [ebp+12]
        push dword ptr [ebp+8]
        mov ecx, edi
        call 0xa7bb60
    bitmap_done:
        pop edi
        pop esi
        pop ebp
        ret 12
    """
    # The purchase packet has one slot per category and {0,0} means "unchanged".
    # Dye Removal selects color 0, which has no HeadPalette sequence number, so
    # the native lookup leaves 0 and the reset is indistinguishable from no
    # change. Send the catalogue's documented reset index (-1) instead.
    reset_sentinel = """
        cmp dword ptr [ebp-0x8a8], 0
        jne reset_done
        mov dword ptr [ebp-0x8a8], 0xffffffff
    reset_done:
        jmp 0x8251ca
    """
    # The costume tab is hard-limited to third/fourth jobs (0xdfbc00/0xdfbca0).
    # Also allow any job that has CostumeChange rows in the loaded Lua table,
    # e.g. class lineage outfits for second/transcendent jobs.
    costume_count = """
        push ebp
        mov ebp, esp
        sub esp, 4
        push ebx
        push esi
        push edi
        mov dword ptr [ebp-4], 0
        mov ecx, 0x1732638
        call 0xdddfe0
        lea ecx, [ebp-4]
        push ecx
        push eax
        push 0x10df238
        sub esp, 24
        mov ebx, esp
        mov dword ptr [ebx], 0
        mov dword ptr [ebx+16], 0
        mov dword ptr [ebx+20], 15
        push 48
        mov ecx, ebx
        call 0x4fa050
        mov [ebx], eax
        mov dword ptr [ebx+16], 26
        mov dword ptr [ebx+20], 47
        mov edi, eax
        mov esi, 0x112f314
        mov ecx, 27
        cld
        rep movsb
        push dword ptr [0x1738010]
        call 0xafc9a0
        add esp, 40
        mov eax, [ebp-4]
        pop edi
        pop esi
        pop ebx
        mov esp, ebp
        pop ebp
        ret
    """
    costume_tab = f"""
        call {COSTUME_COUNT}
        test eax, eax
        jg 0x82970d
        push 0x88
        jmp 0x8296be
    """
    costume_click = f"""
        call {COSTUME_COUNT}
        test eax, eax
        jg 0x82dea7
        cmp esi, {COSTUME_TAB_ID}
        jmp 0x82dea1
    """
    # Favorites key: the native character name (0xe08c70, ecx = session),
    # truncated, plus "@job". Favorites saved by another job keep their entries
    # in the file but are not shown, and return when the character changes back.
    fav_name = f"""
        push esi
        push edi
        call 0xe08c70
        mov esi, eax
        mov edi, {FAV_BUFFER}
        mov ecx, {FAV_NAME_CHARS}
    fav_copy:
        mov al, [esi]
        test al, al
        jz fav_copied
        mov [edi], al
        inc esi
        inc edi
        dec ecx
        jnz fav_copy
    fav_copied:
        mov byte ptr [edi], 0
        mov ecx, 0x1732638
        call 0xdddfe0
        push eax
        push {FAV_FORMAT}
        push {24 - 1 - FAV_NAME_CHARS + 1}
        push edi
        call 0x602b00
        add esp, 16
        mov eax, {FAV_BUFFER}
        pop edi
        pop esi
        ret
    """
    result = bytearray(4096)
    used = bytearray(4096)
    listing = []

    def place(name, address, raw):
        start = address - BASE
        assert 0 <= start and start + len(raw) <= len(result), (name, hex(address))
        assert not any(used[start:start+len(raw)]), f"{name} overlaps another payload block"
        used[start:start+len(raw)] = bytes([1]) * len(raw)
        result[start:start+len(raw)] = raw

    # Runtime variables: hair color count and the favorites key buffer.
    place("COUNT", COUNT, bytes(4))
    place("FAV_BUFFER", FAV_BUFFER, bytes(32))
    place("FAV_FORMAT", FAV_FORMAT, b"@%d\0")
    for name, address, asm in [("create", CREATE, create), ("button", BUTTON, button),
                               ("lookup", LOOKUP, lookup), ("dispatch", DISPATCH, dispatch),
                               ("draw", DRAW, draw), ("preview_draw", PREVIEW_DRAW, preview_draw),
                               ("label", LABEL, label), ("bitmap", BITMAP, bitmap),
                               ("reset_sentinel", RESET_SENTINEL, reset_sentinel),
                               ("costume_count", COSTUME_COUNT, costume_count),
                               ("costume_tab", COSTUME_TAB, costume_tab),
                               ("costume_click", COSTUME_CLICK, costume_click),
                               ("fav_name", FAV_NAME, fav_name)]:
        code = assemble(asm, address)
        place(name, address, code)
        listing.append(f"; {name} at 0x{address:08x}\n{asm}")
    for address, value in [(FORMAT, "Hair Color %d/%d"), (SEQ_NAME, seq), (GOODS_NAME, goods),
                           (STYLE_FORMAT, "Hairstyle %d/%d"), (CLOTH_FORMAT, "Clothing Color %d/%d"),
                           (SIZE_NAME, "StylingShop_GetSizeInTable")]:
        place(value, address, value.encode("ascii") + b"\0")
    for address, value in [(HAIR_BOX_PATH, HAIR_BOX_BMP), (STYLE_BOX_PATH, STYLE_BOX_BMP)]:
        place(value, address, value.encode("cp949") + b"\0")
    return bytes(result), "\n".join(listing)


def build(source):
    if hashlib.sha256(source).hexdigest() != SOURCE_SHA256:
        raise ValueError("Unsupported client. The input must match the supported SHA-256 exactly.")
    pe = pefile.PE(data=source)
    code, listing = payload()
    patches = []

    def change(offset, new):
        patches.append((offset, source[offset:offset+len(new)], new))

    def va(address, new):
        change(pe.get_offset_from_rva(address-pe.OPTIONAL_HEADER.ImageBase), new)

    va(0x828556, assemble(f"jmp {CREATE}", 0x828556) + b"\x90" * 3)
    va(0x82D156, assemble(f"jmp {DISPATCH}", 0x82D156) + b"\x90" * 2)
    va(0x112E8A4, struct.pack("<I", DRAW))
    va(0x112E38C, struct.pack("<I", PREVIEW_DRAW))
    # Move the existing two arrow pairs above the character preview.
    for address, y in [(0x827143, 32), (0x8271DC, 32), (0x827278, 54), (0x827311, 54)]:
        va(address, bytes([y]))
    # Leave the complete native Doram guard and rejection dialog intact.
    # Redirect its exits past the obsolete image-button loop.
    va(0x82D2DF, assemble("jmp 0x82d32c", 0x82D2DF))
    va(0x82D30F, assemble("jmp 0x82d362", 0x82D30F))
    # Purchase packet: route the selected hair color slot through RESET_SENTINEL.
    va(0x8250B0, assemble(f"jmp {RESET_SENTINEL}", 0x8250B0))
    # Costume tab: creation (enabled/disabled) and click handler.
    va(0x8296B9, assemble(f"jmp {COSTUME_TAB}", 0x8296B9))
    va(0x82DE9B, assemble(f"jmp {COSTUME_CLICK}", 0x82DE9B) + b"\x90")
    # Favorites file: every read/write of the character name uses FAV_NAME.
    for address in FAV_NAME_CALLS:
        va(address, assemble(f"call {FAV_NAME}", address))
    file_align = pe.OPTIONAL_HEADER.FileAlignment
    raw_offset = (len(source)+file_align-1) // file_align * file_align
    rva = BASE-pe.OPTIONAL_HEADER.ImageBase
    assert rva == pe.OPTIONAL_HEADER.SizeOfImage
    section_header = pe.sections[-1].get_file_offset() + 40
    assert section_header+40 <= pe.OPTIONAL_HEADER.SizeOfHeaders
    assert source[section_header:section_header+40] == bytes(40)
    header = struct.pack("<8sIIIIIIHHI", b".stynum\0", len(code), rva, len(code),
                         raw_offset, 0, 0, 0, 0, 0xE0000020)
    change(section_header, header)
    change(pe.FILE_HEADER.get_field_absolute_offset("NumberOfSections"),
           struct.pack("<H", pe.FILE_HEADER.NumberOfSections+1))
    change(pe.OPTIONAL_HEADER.get_field_absolute_offset("SizeOfImage"), struct.pack("<I", rva+4096))
    change(pe.OPTIONAL_HEADER.get_field_absolute_offset("SizeOfCode"),
           struct.pack("<I", pe.OPTIONAL_HEADER.SizeOfCode+len(code)))
    change(pe.OPTIONAL_HEADER.get_field_absolute_offset("CheckSum"), bytes(4))
    patches.append((len(source), b"", bytes(raw_offset-len(source))+code))
    output = bytearray(source)
    for offset, old, new in patches:
        output[offset:offset+len(old)] = new
    return bytes(output), patches, listing


# Recipe entry kinds. The patcher validates each site instead of the whole file:
# a SITE must hold its original or its patched bytes; SECTION (the .stynum
# header slot) tells whether the payload is already appended; APPEND is the
# payload, always rewritten so older Stylist patches are upgraded.
SITE, SECTION, APPEND = 0, 1, 2


def recipe(source, output, patches):
    result = bytearray(b"STYNUM02")
    result.extend(struct.pack("<III", len(source), len(output), len(patches)))
    for offset, old, new in patches:
        kind = APPEND if not old else SECTION if new.startswith(b".stynum\0") else SITE
        assert kind == APPEND or len(old) == len(new)
        result.extend(struct.pack("<IIII", kind, offset, len(old), len(new)))
        result.extend(old)
        result.extend(new)
    return bytes(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--artifacts", type=Path, default=Path(__file__).parent / "generated")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    source = args.source.read_bytes()
    output, patches, listing = build(source)
    args.artifacts.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(output).hexdigest()
    (args.artifacts / "patch.bin").write_bytes(recipe(source, output, patches))
    (args.artifacts / "payload.asm").write_text(listing, encoding="utf-8")
    (args.artifacts / "manifest.json").write_text(json.dumps({
        "source_sha256": SOURCE_SHA256, "output_sha256": digest,
        "section": ".stynum", "patches": [
            {"offset": offset, "before": old.hex(), "after": new.hex()}
            for offset, old, new in patches if old]}, indent=2)+"\n", encoding="utf-8")
    if args.output:
        # Exclusive creation makes accidentally replacing the source impossible.
        with args.output.open("xb") as target:
            target.write(output)
    print(f"Supported input: {SOURCE_SHA256}\nPatched output: {digest}")


if __name__ == "__main__":
    main()
