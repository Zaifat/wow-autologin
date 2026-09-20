# -*- coding: utf-8 -*-
"""The class / race icons taken from the client: the MPQ reader, the BLP2
decoder and the slicing of the character-create atlases. A small archive is
built here on the fly, so the suite needs no game files."""
import importlib.util, os, struct, sys, tempfile, zlib

spec = importlib.util.spec_from_file_location("wowart",
                                              os.path.abspath("wowart.py"))
W = importlib.util.module_from_spec(spec)
spec.loader.exec_module(W)

spec2 = importlib.util.spec_from_file_location("launcher",
                                               os.path.abspath("launcher.py"))
L = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(L)

tmp = tempfile.mkdtemp(prefix="wowmgr_icons_")
ok = []


def check(name, cond):
    ok.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name)


# ── a minimal MPQ writer, only for these tests ────────────────────────────
def _encrypt(data, key):
    """The MPQ cipher is its own inverse only per 4-byte word, so encryption
    is written out separately from wowart's decryption."""
    out = bytearray(data)
    seed2 = 0xEEEEEEEE
    for i in range(len(data) // 4):
        seed2 = (seed2 + W._CRYPT[0x400 + (key & 0xFF)]) & 0xFFFFFFFF
        plain = struct.unpack_from("<I", out, i * 4)[0]
        enc = (plain ^ (key + seed2)) & 0xFFFFFFFF
        struct.pack_into("<I", out, i * 4, enc)
        key = (((~key << 0x15) + 0x11111111) | (key >> 0x0B)) & 0xFFFFFFFF
        seed2 = (plain + seed2 + (seed2 << 5) + 3) & 0xFFFFFFFF
    return bytes(out)


def write_mpq(path, files, sector=4096, single=False, lead=0):
    """`files` is {archive path: bytes}. Stores each file zlib-compressed,
    either as sectors or as one unit, after `lead` bytes of junk."""
    head_len = 32                     # file positions are archive-relative
    hash_n = 16
    while hash_n < len(files) * 2:
        hash_n *= 2
    hash_tbl = [[0xFFFFFFFF, 0xFFFFFFFF, 0xFFFF, 0xFFFF, 0xFFFFFFFF]
                for _ in range(hash_n)]
    blocks, body = [], bytearray()
    for i, (name, data) in enumerate(files.items()):
        pos = len(body)
        if single:
            packed = zlib.compress(data)
            body += b"\x02" + packed if len(packed) + 1 < len(data) else data
            flags = 0x80000000 | 0x00000200 | 0x01000000
        else:
            n = (len(data) + sector - 1) // sector
            chunks = []
            for k in range(n):
                raw = data[k * sector:(k + 1) * sector]
                packed = b"\x02" + zlib.compress(raw)
                chunks.append(packed if len(packed) < len(raw) else raw)
            offs, at = [], (n + 1) * 4
            for c in chunks:
                offs.append(at)
                at += len(c)
            offs.append(at)
            body += struct.pack("<%dI" % (n + 1), *offs)
            for c in chunks:
                body += c
            flags = 0x80000000 | 0x00000200
        blocks.append((head_len + pos, len(body) - pos, len(data),
                       flags))
        slot = W._hash(name, 0) % hash_n
        while hash_tbl[slot][4] != 0xFFFFFFFF:
            slot = (slot + 1) % hash_n
        hash_tbl[slot] = [W._hash(name, 1), W._hash(name, 2), 0, 0, i]

    ht = b"".join(struct.pack("<IIHHI", *h) for h in hash_tbl)
    bt = b"".join(struct.pack("<IIII", *b) for b in blocks)
    ht = _encrypt(ht, W._hash("(hash table)", 3))
    bt = _encrypt(bt, W._hash("(block table)", 3))
    shift = 0
    while (512 << shift) < sector:
        shift += 1
    hdr = struct.pack("<4sIIHHIIII", b"MPQ\x1a", head_len, 0, 0, shift,
                      head_len + len(body), head_len + len(body) + len(ht),
                      hash_n, len(blocks))
    with open(path, "wb") as fh:
        fh.write(b"\x00" * lead)
        fh.write(hdr + bytes(body) + ht + bt)


def make_blp(w, h, pixel):
    """A palettised BLP2 whose colours come from pixel(x, y) -> index, with a
    palette of 256 distinct colours."""
    pal = bytearray()
    for i in range(256):
        pal += bytes((i, 255 - i, (i * 7) & 0xFF, 0))       # BGRA
    body = bytearray()
    for y in range(h):
        for x in range(w):
            body.append(pixel(x, y))
    body += b"\xFF" * (w * h)                               # 8-bit alpha
    head = struct.pack("<4sIBBBBII", b"BLP2", 1, 1, 8, 0, 0, w, h)
    offs = [148 + 1024] + [0] * 15
    lens = [len(body)] + [0] * 15
    return (head + struct.pack("<16I", *offs) + struct.pack("<16I", *lens)
            + bytes(pal) + bytes(body))


# ── the reader round-trips ────────────────────────────────────────────────
data_dir = os.path.join(tmp, "WOW", "Data")
os.makedirs(data_dir)
small = b"hello wow" * 3
big = bytes(bytearray((i * 37) & 0xFF for i in range(30000)))
arc = os.path.join(data_dir, "test.MPQ")
write_mpq(arc, {r"Interface\Small.txt": small, r"Interface\Big.bin": big})
m = W.Archive(arc)
check("a small file comes back byte for byte",
      m.read(r"Interface\Small.txt") == small)
check("a multi-sector file comes back byte for byte",
      m.read(r"Interface\Big.bin") == big)
check("the lookup is case-insensitive and takes slashes",
      m.read("interface/small.TXT") == small)
check("a missing file is None", m.read(r"Interface\Nope.txt") is None)
m.close()

one = os.path.join(data_dir, "single.MPQ")
write_mpq(one, {r"Interface\Big.bin": big}, single=True, lead=1024)
m = W.Archive(one)
check("a single-unit file in a shifted archive still reads",
      m.read(r"Interface\Big.bin") == big)
m.close()

# ── BLP2 ──────────────────────────────────────────────────────────────────
blp = make_blp(8, 4, lambda x, y: (x + y * 8) & 0xFF)
img = W.blp_to_image(blp)
check("BLP2 keeps its size", img.size == (8, 4))
check("BLP2 palette entries are BGRA", img.getpixel((1, 0))[:3] == (7, 254, 1))
check("BLP2 alpha is read", img.getpixel((3, 2))[3] == 255)

# ── slicing the atlases ───────────────────────────────────────────────────
# Each cell of the fake atlas is one flat colour, so a mis-sliced icon is
# immediately visible as the wrong colour.
def cell_index(cols, rows, cell_w, cell_h):
    return lambda x, y: (x // cell_w) + (y // cell_h) * cols


classes = make_blp(256, 256, cell_index(4, 4, 64, 64))
races = make_blp(512, 256, cell_index(8, 4, 64, 64))
write_mpq(os.path.join(data_dir, "art.MPQ"),
          {W.CLASS_ATLAS: classes, W.RACE_ATLAS: races})

out = os.path.join(tmp, "icons")
n = W.extract_icons(os.path.join(tmp, "WOW"), out, size=32)
check("every class and race icon is written", n == 30)
check("icons are saved at the asked size",
      __import__("PIL.Image", fromlist=["Image"]).open(
          os.path.join(out, "class_warrior.png")).size == (32, 32))


def cell_of(path):
    from PIL import Image
    r, g, _b, _a = Image.open(path).convert("RGBA").getpixel((16, 16))
    return g                                   # palette index n -> g = 255-n


check("the warrior icon is the first class cell",
      cell_of(os.path.join(out, "class_warrior.png")) == 255)
check("the death knight icon is the second cell of the third row",
      cell_of(os.path.join(out, "class_deathknight.png")) == 255 - 9)
check("the male orc portrait is the fourth cell of the second row",
      cell_of(os.path.join(out, "race_orc_male.png")) == 255 - 11)
check("the female orc portrait sits two rows lower",
      cell_of(os.path.join(out, "race_orc_female.png")) == 255 - 27)

check("a race lookup defaults to the male portrait",
      W.icon_path(out, "race", "orc") == W.icon_path(out, "race", "orc_male"))
check("'undead' is the same race as 'scourge'",
      W.icon_path(out, "race", "Undead_Female")
      == W.icon_path(out, "race", "scourge_female"))
check("an unknown race has no icon", W.icon_path(out, "race", "murloc") is None)
check("an empty key has no icon", W.icon_path(out, "class", "") is None)

# ── the manager side ──────────────────────────────────────────────────────
check("class names map onto the atlas keys",
      L.class_icon_key("Рыцарь смерти") == "deathknight"
      and L.class_icon_key("Воин") == "warrior")
check("every class has an icon in the atlas",
      all(L.class_icon_key(c) in W.CLASS_CELLS for c in L.CLASS_COLORS))
check("every race the addon reports has a portrait",
      all(W.RACE_ALIASES.get(r, r) + "_male" in W.RACE_CELLS
          for r in L.RACE_BADGES))

L.CONFIG_FILE = os.path.join(tmp, "characters.json")
L._config_dir = lambda: tmp
check("extraction from a folder that is not a client is refused",
      L.extract_game_icons(os.path.join(tmp, "nowhere")) is False)
check("icons land next to the config",
      L.extract_game_icons(os.path.join(tmp, "WOW"))
      and os.path.isfile(os.path.join(L.icons_dir(), "class_warrior.png")))

print()
bad = [n for n, v in ok if not v]
print("%d/%d passed" % (len(ok) - len(bad), len(ok)))
sys.exit(1 if bad else 0)
