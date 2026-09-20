# -*- coding: utf-8 -*-
"""Class and race icons taken from the player's own game client.

The manager ships no artwork: it reads the two character-creation atlases
straight out of the installed client's MPQ archives and slices them into
small PNGs next to the config. That needs a minimal read-only MPQ reader and
a BLP2 decoder, both of which live here.

    extract_icons(r"E:\\WOW", out_dir)  ->  {"class_warrior": "…/….png", …}
"""
import os
import struct
import zlib

CLASS_ATLAS = r"Interface\Glues\CharacterCreate\UI-CharacterCreate-Classes.blp"
RACE_ATLAS = r"Interface\Glues\CharacterCreate\UI-CharacterCreate-Races.blp"

# Cell of each class in the 4x4 atlas — the same layout the game's own
# CLASS_ICON_TCOORDS uses.
CLASS_CELLS = {
    "warrior": (0, 0), "mage": (1, 0), "rogue": (2, 0), "druid": (3, 0),
    "hunter": (0, 1), "shaman": (1, 1), "priest": (2, 1), "warlock": (3, 1),
    "paladin": (0, 2), "deathknight": (1, 2),
}
# Races: column per race, row per faction block; the bottom two rows are the
# female portraits.
RACE_CELLS = {}
for _col, _r in enumerate(("human", "dwarf", "gnome", "nightelf", "draenei")):
    RACE_CELLS[_r + "_male"] = (_col, 0)
    RACE_CELLS[_r + "_female"] = (_col, 2)
for _col, _r in enumerate(("tauren", "scourge", "troll", "orc", "bloodelf")):
    RACE_CELLS[_r + "_male"] = (_col, 1)
    RACE_CELLS[_r + "_female"] = (_col, 3)
RACE_ALIASES = {"undead": "scourge"}


# ── MPQ ────────────────────────────────────────────────────────────────────
def _build_crypt_table():
    tbl = [0] * 0x500
    seed = 0x00100001
    for i in range(0x100):
        idx = i
        for _ in range(5):
            seed = (seed * 125 + 3) % 0x2AAAAB
            hi = (seed & 0xFFFF) << 16
            seed = (seed * 125 + 3) % 0x2AAAAB
            tbl[idx] = hi | (seed & 0xFFFF)
            idx += 0x100
    return tbl


_CRYPT = _build_crypt_table()


def _hash(name, kind):
    seed1, seed2 = 0x7FED7FED, 0xEEEEEEEE
    for ch in name.upper().replace("/", "\\").encode("latin-1", "replace"):
        seed1 = (_CRYPT[(kind << 8) + ch] ^ (seed1 + seed2)) & 0xFFFFFFFF
        seed2 = (ch + seed1 + seed2 + (seed2 << 5) + 3) & 0xFFFFFFFF
    return seed1


def _decrypt(data, key):
    out = bytearray(data)
    seed2 = 0xEEEEEEEE
    for i in range(len(data) // 4):
        seed2 = (seed2 + _CRYPT[0x400 + (key & 0xFF)]) & 0xFFFFFFFF
        v = (struct.unpack_from("<I", out, i * 4)[0] ^ (key + seed2)) \
            & 0xFFFFFFFF
        struct.pack_into("<I", out, i * 4, v)
        key = (((~key << 0x15) + 0x11111111) | (key >> 0x0B)) & 0xFFFFFFFF
        seed2 = (v + seed2 + (seed2 << 5) + 3) & 0xFFFFFFFF
    return bytes(out)


_EXISTS = 0x80000000
_SINGLE_UNIT = 0x01000000
_SECTOR_CRC = 0x04000000
_PATCH_FILE = 0x00100000
_ENCRYPTED = 0x00010000
_FIX_KEY = 0x00020000
_COMPRESSED = 0x00000300      # zlib/bzip2 (0x200) or PKWARE implode (0x100)


def _inflate(chunk, want):
    """One stored sector -> raw bytes."""
    if len(chunk) >= want:            # stored as-is when nothing was gained
        return chunk[:want]
    mask, body = chunk[0], chunk[1:]
    if mask == 0x02:
        return zlib.decompress(body)
    if mask == 0x10:
        import bz2
        return bz2.decompress(body)
    raise ValueError("MPQ compression 0x%02X is not supported" % mask)


class Archive(object):
    """Read-only MPQ (version 1) — enough to pull a known file out by name."""

    def __init__(self, path):
        self.fh = open(path, "rb")
        self.base = self._find_header()
        (_hdr, _size, _ver, block_shift, hash_pos, block_pos,
         hash_n, block_n) = struct.unpack("<IIHHIIII", self.fh.read(28))
        self.sector = 512 << block_shift
        self.fh.seek(self.base + hash_pos)
        ht = _decrypt(self.fh.read(hash_n * 16), _hash("(hash table)", 3))
        self.fh.seek(self.base + block_pos)
        bt = _decrypt(self.fh.read(block_n * 16), _hash("(block table)", 3))
        self._hash = [struct.unpack_from("<IIHHI", ht, i * 16)
                      for i in range(hash_n)]
        self._block = [struct.unpack_from("<IIII", bt, i * 16)
                       for i in range(block_n)]

    def _find_header(self):
        off = 0
        while off <= 0x100000:
            self.fh.seek(off)
            magic = self.fh.read(4)
            if magic == b"MPQ\x1a":
                return off
            if magic == b"MPQ\x1b":              # user-data block in front
                off += struct.unpack("<III", self.fh.read(12))[2]
                continue
            off += 512
        raise ValueError("not an MPQ archive")

    def close(self):
        try:
            self.fh.close()
        except OSError:
            pass

    def _lookup(self, name):
        n = len(self._hash)
        if not n:
            return None
        start = _hash(name, 0) % n
        want_a, want_b = _hash(name, 1), _hash(name, 2)
        i = start
        while True:
            a, b, _loc, _plat, block = self._hash[i]
            if block == 0xFFFFFFFF:              # empty and never used
                return None
            if a == want_a and b == want_b and block != 0xFFFFFFFE:
                return block
            i = (i + 1) % n
            if i == start:
                return None

    def read(self, name):
        """File contents, or None when this archive doesn't hold it."""
        idx = self._lookup(name)
        if idx is None or idx >= len(self._block):
            return None
        pos, packed, size, flags = self._block[idx]
        if not flags & _EXISTS or flags & _PATCH_FILE or not size:
            return None
        self.fh.seek(self.base + pos)
        raw = self.fh.read(packed)
        key = None
        if flags & _ENCRYPTED:
            key = _hash(name.split("\\")[-1], 3)
            if flags & _FIX_KEY:
                key = ((key + pos) ^ size) & 0xFFFFFFFF
        if not flags & _COMPRESSED:
            return raw[:size]
        if flags & _SINGLE_UNIT:
            return _inflate(_decrypt(raw, key) if key is not None else raw,
                            size)
        sectors = (size + self.sector - 1) // self.sector
        head = (sectors + 1 + (1 if flags & _SECTOR_CRC else 0)) * 4
        table = raw[:head]
        if key is not None:
            table = _decrypt(table, (key - 1) & 0xFFFFFFFF)
        offs = struct.unpack("<%dI" % (len(table) // 4), table)
        out = bytearray()
        for i in range(sectors):
            chunk = raw[offs[i]:offs[i + 1]]
            if key is not None:
                chunk = _decrypt(chunk, (key + i) & 0xFFFFFFFF)
            out += _inflate(chunk, min(self.sector, size - len(out)))
        return bytes(out[:size])


# ── BLP2 ───────────────────────────────────────────────────────────────────
def blp_to_image(data):
    """Decode a BLP2 texture (palettised, DXT1/3/5 or raw BGRA) to RGBA."""
    from PIL import Image
    if data[:4] != b"BLP2":
        raise ValueError("not a BLP2 texture")
    (_magic, _kind, enc, alpha_bits, alpha_enc, _mips, w, h) = \
        struct.unpack_from("<IIBBBBII", data, 0)
    mip_off = struct.unpack_from("<16I", data, 20)
    mip_len = struct.unpack_from("<16I", data, 84)
    palette = struct.unpack_from("<1024B", data, 148)
    body = data[mip_off[0]:mip_off[0] + mip_len[0]]
    if enc == 1:                                   # 256-colour palette
        px = bytearray()
        n = w * h
        for i in range(n):
            p = body[i] * 4
            px += bytes((palette[p + 2], palette[p + 1], palette[p], 255))
        if alpha_bits == 8:
            for i in range(n):
                px[i * 4 + 3] = body[n + i]
        elif alpha_bits == 1:
            bits = body[n:]
            for i in range(n):
                px[i * 4 + 3] = 255 if bits[i >> 3] & (1 << (i & 7)) else 0
        return Image.frombytes("RGBA", (w, h), bytes(px))
    if enc == 2:
        return _decode_dxt(body, w, h, {0: 1, 1: 3, 7: 5}.get(alpha_enc, 1))
    if enc == 3:                                   # straight BGRA
        b = bytearray(body[:w * h * 4])
        b[0::4], b[2::4] = b[2::4], b[0::4]
        return Image.frombytes("RGBA", (w, h), bytes(b))
    raise ValueError("BLP encoding %d is not supported" % enc)


def _decode_dxt(body, w, h, variant):
    from PIL import Image
    img = Image.new("RGBA", (w, h))
    px = img.load()
    stride = 8 if variant == 1 else 16
    at = 0
    for by in range(0, h, 4):
        for bx in range(0, w, 4):
            block = body[at:at + stride]
            at += stride
            alpha = [255] * 16
            if variant == 3:
                for k in range(16):
                    alpha[k] = ((block[k // 2] >> (4 * (k % 2))) & 0xF) * 17
                colour = block[8:]
            elif variant == 5:
                a0, a1 = block[0], block[1]
                bits = int.from_bytes(block[2:8], "little")
                ramp = [a0, a1]
                if a0 > a1:
                    ramp += [((7 - j) * a0 + j * a1) // 7 for j in range(1, 7)]
                else:
                    ramp += [((5 - j) * a0 + j * a1) // 5 for j in range(1, 5)]
                    ramp += [0, 255]
                for k in range(16):
                    alpha[k] = ramp[(bits >> (3 * k)) & 7]
                colour = block[8:]
            else:
                colour = block
            c0, c1 = struct.unpack_from("<HH", colour, 0)
            idx = struct.unpack_from("<I", colour, 4)[0]

            def rgb565(c):
                return (((c >> 11) & 31) * 255 // 31,
                        ((c >> 5) & 63) * 255 // 63,
                        (c & 31) * 255 // 31)

            e0, e1 = rgb565(c0), rgb565(c1)
            if c0 > c1 or variant != 1:
                cols = [e0, e1,
                        tuple((2 * e0[j] + e1[j]) // 3 for j in range(3)),
                        tuple((e0[j] + 2 * e1[j]) // 3 for j in range(3))]
                clear = (False, False, False, False)
            else:
                cols = [e0, e1,
                        tuple((e0[j] + e1[j]) // 2 for j in range(3)),
                        (0, 0, 0)]
                clear = (False, False, False, True)
            for k in range(16):
                x, y = bx + (k % 4), by + (k // 4)
                if x < w and y < h:
                    ci = (idx >> (2 * k)) & 3
                    px[x, y] = cols[ci] + (0 if clear[ci] else alpha[k],)
    return img


# ── extraction ─────────────────────────────────────────────────────────────
def data_archives(wow_dir):
    """Every MPQ of a client, most likely to hold interface art first."""
    out = []
    data = os.path.join(wow_dir, "Data")
    dirs = [data]
    try:
        dirs += [os.path.join(data, d) for d in sorted(os.listdir(data))
                 if os.path.isdir(os.path.join(data, d))]
    except OSError:
        return out
    for d in dirs:
        try:
            names = sorted(os.listdir(d))
        except OSError:
            continue
        for n in names:
            p = os.path.join(d, n)
            if n.lower().endswith(".mpq") and os.path.isfile(p):
                out.append(p)
    # The atlases live in the locale archives, which are also the small ones;
    # trying those first saves reading a 4 GB archive's tables for nothing.
    out.sort(key=lambda p: os.path.getsize(p))
    return out


def _read_from_client(wow_dir, names):
    """Read several files out of a client, opening each archive only once."""
    found = {}
    for path in data_archives(wow_dir):
        if len(found) == len(names):
            break
        try:
            mpq = Archive(path)
        except (OSError, ValueError, struct.error):
            continue
        try:
            for name in names:
                if name in found:
                    continue
                try:
                    blob = mpq.read(name)
                except (ValueError, struct.error, zlib.error, OSError):
                    blob = None
                if blob:
                    found[name] = blob
        finally:
            mpq.close()
    return found


def extract_icons(wow_dir, out_dir, size=64):
    """Slice the class and race atlases of `wow_dir` into PNGs in `out_dir`.
    Returns the number of icons written; 0 means the client had nothing."""
    from PIL import Image
    blobs = _read_from_client(wow_dir, [CLASS_ATLAS, RACE_ATLAS])
    if not blobs:
        return 0
    os.makedirs(out_dir, exist_ok=True)
    written = 0
    for atlas, cells, prefix, cols, rows in (
            (CLASS_ATLAS, CLASS_CELLS, "class", 4, 4),
            (RACE_ATLAS, RACE_CELLS, "race", 8, 4)):
        blob = blobs.get(atlas)
        if not blob:
            continue
        sheet = blp_to_image(blob)
        cw, ch = sheet.width // cols, sheet.height // rows
        for key, (col, row) in cells.items():
            cell = sheet.crop((col * cw, row * ch, (col + 1) * cw,
                               (row + 1) * ch))
            if (cw, ch) != (size, size):
                cell = cell.resize((size, size), Image.LANCZOS)
            cell.save(os.path.join(out_dir, "%s_%s.png" % (prefix, key)))
            written += 1
    return written


def icon_path(out_dir, prefix, key):
    """Path of one extracted icon, or None when it isn't there."""
    if not key:
        return None
    key = str(key).lower()
    if prefix == "race":
        base, _, sex = key.partition("_")
        base = RACE_ALIASES.get(base, base)
        key = base + "_" + (sex or "male")
    p = os.path.join(out_dir, "%s_%s.png" % (prefix, key))
    return p if os.path.isfile(p) else None
