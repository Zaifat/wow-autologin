# -*- coding: utf-8 -*-
"""Smoke-test the pure helpers touched by the audit."""
import importlib.util, io, os, sys, tempfile, zipfile, json

ROOT = os.path.abspath('.')
spec = importlib.util.spec_from_file_location("launcher", os.path.join(ROOT, "launcher.py"))
L = importlib.util.module_from_spec(spec)
spec.loader.exec_module(L)

tmp = tempfile.mkdtemp(prefix="wowmgr_smoke_")
ok = []


def check(name, cond):
    ok.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name)


# ── config round-trip: atomic save + .bak fallback ──────────────────────────
L.CONFIG_FILE = os.path.join(tmp, "characters.json")
cfg = L._default_cfg()
cfg["characters"] = [{"name": "Тест", "account": "acc1", "password": "p@ss",
                      "class": "Паладин", "realm": "R", "realmlist": "logon.x",
                      "totp_secret": "JBSWY3DPEHPK3PXP"}]
cfg["encrypt_secrets"] = False
L.save_cfg(cfg)
check("save_cfg wrote the file", os.path.isfile(L.CONFIG_FILE))
check("save_cfg left no .tmp", not os.path.isfile(L.CONFIG_FILE + ".tmp"))
back = L.load_cfg()
tchar = next((e for e in back["characters"] if e.get("name") == "Тест"), {})
check("round-trip keeps the character", tchar.get("password") == "p@ss")

# second save produces a .bak
L.save_cfg(cfg)
check("save_cfg keeps a .bak", os.path.isfile(L.CONFIG_FILE + ".bak"))

# corrupt the live file -> must fall back to .bak instead of blowing up
with io.open(L.CONFIG_FILE, "w", encoding="utf-8") as f:
    f.write('{"characters": [{"name": "Те')
rescued = L.load_cfg()
check("corrupt config falls back to .bak",
      any(e.get("name") == "Тест" for e in rescued["characters"]))

# ── realmlist ──────────────────────────────────────────────────────────────
wow = os.path.join(tmp, "wow")
os.makedirs(wow, exist_ok=True)
L.update_realmlist(wow, "logon.wowcircle.me")
txt = io.open(os.path.join(wow, "realmlist.wtf"), encoding="ascii").read()
check("realmlist written", txt.strip() == "set realmlist logon.wowcircle.me")
try:
    L.update_realmlist(wow, "логон.рф")
    check("non-ascii realmlist rejected", False)
except RuntimeError:
    check("non-ascii realmlist rejected", True)

# ── restore: zip-slip must be refused ──────────────────────────────────────
evil = os.path.join(tmp, "evil.zip")
with zipfile.ZipFile(evil, "w") as z:
    z.writestr("WTF/../../pwned.txt", "nope")
    z.writestr("WTF/Config.wtf", "SET gxResolution \"1920x1080\"")
L._restore_snapshot(wow, evil)
check("zip-slip blocked", not os.path.exists(os.path.join(tmp, "pwned.txt"))
      and not os.path.exists(os.path.join(os.path.dirname(tmp), "pwned.txt")))
check("normal member restored", os.path.isfile(os.path.join(wow, "WTF", "Config.wtf")))

# ── autologin.json shape ───────────────────────────────────────────────────
data = L._build_autologin_json(cfg["characters"][0], "logon.x")
check("autologin json fields",
      data["login"] == "acc1" and data["character"] == "Тест"
      and data["totp_secret"] == "JBSWY3DPEHPK3PXP")

L._write_autologin_json(wow, cfg["characters"][0], "logon.x")
check("autologin.json written", os.path.isfile(os.path.join(wow, "autologin.json")))
L.drop_stale_autologin_json(wow)
check("stale autologin.json removed",
      not os.path.isfile(os.path.join(wow, "autologin.json")))

# ── TOTP against the RFC 6238 SHA-1 test vector ────────────────────────────
# secret = "12345678901234567890" -> base32 GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ
check("totp rfc6238 t=59", L.compute_totp("GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ", t=59) == "287082")
check("totp rfc6238 t=1111111109",
      L.compute_totp("GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ", t=1111111109) == "081804")
check("otpauth uri parsed",
      L.normalize_totp_secret("otpauth://totp/x?secret=JBSWY3DPEHPK3PXP&issuer=y")
      == "JBSWY3DPEHPK3PXP")

# ── IPC token ──────────────────────────────────────────────────────────────
L._config_dir = lambda: tmp
t1 = L._ipc_token()
t2 = L._ipc_token()
check("ipc token stable and long", t1 == t2 and len(t1) >= 16)

# ── SavedVariables parser ──────────────────────────────────────────────────
sv = '''
WowManagerDB = {
    ["Realm.Тест"] = {
        ["name"] = "Тест", ["gold"] = 123456, ["level"] = 80,
        ["profs"] = { "Кузнечное дело 450/450", }, ["locks"] = {},
    },
    ["__relog"] = { ["char"] = "Другой", ["at"] = 1700000000 },
}
'''
parsed = L.parse_lua_savedvars(sv)
db = parsed["WowManagerDB"]
check("lua parser reads records", db["Realm.Тест"]["gold"] == 123456)
check("lua parser reads relog", db["__relog"]["char"] == "Другой")

print()
bad = [n for n, v in ok if not v]
print("%d/%d passed" % (len(ok) - len(bad), len(ok)))
sys.exit(1 if bad else 0)
