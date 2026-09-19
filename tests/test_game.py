# -*- coding: utf-8 -*-
"""4 GB flag, graphics presets, anti-AFK switch and the addon flags."""
import importlib.util, io, json, os, shutil, struct, sys, tempfile, time

spec = importlib.util.spec_from_file_location("launcher", os.path.abspath("launcher.py"))
L = importlib.util.module_from_spec(spec)
spec.loader.exec_module(L)

tmp = tempfile.mkdtemp(prefix="wowmgr_game_")
ok = []


def check(name, cond):
    ok.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name)


# ── 4 GB flag on a real PE file ────────────────────────────────────────────
# python.exe is a genuine PE; copy it and clear the flag so there's work to do
exe = os.path.join(tmp, "Wow.exe")
shutil.copy2(sys.executable, exe)
with open(exe, "r+b") as f:
    off = L._coff_characteristics_offset(f)
    f.seek(off)
    flags = struct.unpack("<H", f.read(2))[0]
    f.seek(off)
    f.write(struct.pack("<H", flags & ~L.IMAGE_FILE_LARGE_ADDRESS_AWARE))
before = open(exe, "rb").read()
check("flag starts cleared", not L.is_large_address_aware(exe))
check("ensure sets the flag", L.ensure_large_address_aware(exe)
      and L.is_large_address_aware(exe))
after = open(exe, "rb").read()
diff = [i for i in range(len(before)) if before[i] != after[i]]
check("only the characteristics field changed",
      len(diff) == 1 and diff[0] in (off, off + 1))
check("second call is a no-op", L.ensure_large_address_aware(exe)
      and open(exe, "rb").read() == after)
junk = os.path.join(tmp, "junk.exe")
open(junk, "wb").write(b"not a pe file at all" * 10)
check("a non-PE file is left alone", not L.ensure_large_address_aware(junk)
      and open(junk, "rb").read() == b"not a pe file at all" * 10)

# ── graphics presets ───────────────────────────────────────────────────────
cfg = {"characters": [
    {"name": "", "account": "acc", "graphics": "minimal"},
    {"name": "Twink", "account": "acc", "graphics": ""},
    {"name": "Main", "account": "acc", "graphics": "none"},
    {"name": "Light", "account": "acc", "graphics": "light"},
    {"name": "", "account": "plain"},
    {"name": "Solo", "account": "plain"},
]}
eff = {c["name"] or c["account"]: L.effective_graphics(cfg, c)
       for c in cfg["characters"]}
check("character inherits the account preset", eff["Twink"] == "minimal")
check("'as in game' on a character overrides the account", eff["Main"] == "")
check("a character's own preset wins", eff["Light"] == "light")
check("no preset anywhere means none", eff["Solo"] == "")
check("every preset only uses CVars that exist in 3.3.5a",
      all(n in {"farclip", "groundEffectDensity", "groundEffectDist",
                "environmentDetail", "particleDensity", "weatherDensity",
                "extShadowQuality", "detailDoodadAlpha", "projectedTextures",
                "spellEffectLevel", "maxFPS", "maxFPSBk",
                "Sound_EnableAllSound"}
          for p in L.GRAPHICS_PRESETS.values() for n in p))
check("every preset has a label",
      {k for k, _ in L.GRAPHICS_LABELS if k} == set(L.GRAPHICS_PRESETS))

# Config.wtf snapshot / restore
wow = os.path.join(tmp, "game")
os.makedirs(os.path.join(wow, "WTF"))
conf = os.path.join(wow, "WTF", "Config.wtf")
io.open(conf, "w", encoding="utf-8").write(
    'SET realmList "logon.wowcircle.me"\n'
    'SET farclip "777"\n'
    'SET maxFPS "144"\n'
    'SET gxResolution "1920x1080"\n')
names = L.GRAPHICS_PRESETS["minimal"]
snap = L.read_config_cvars(wow, names)
check("snapshot reads existing values", snap["farclip"] == "777"
      and snap["maxFPS"] == "144")
check("snapshot marks absent CVars", snap["Sound_EnableAllSound"] is None)

# the client exits and writes the preset values (plus a new line) back
io.open(conf, "w", encoding="utf-8").write(
    'SET realmList "logon.wowcircle.me"\n'
    'SET farclip "177"\n'
    'set MAXFPS "30"\n'
    'SET gxResolution "1920x1080"\n'
    'SET Sound_EnableAllSound "0"\n')
check("restore succeeds", L.restore_config_cvars(wow, snap))
text = io.open(conf, encoding="utf-8").read()
check("changed values are put back", 'SET farclip "777"' in text
      and '"144"' in text)
check("a CVar the preset added is removed again",
      "Sound_EnableAllSound" not in text)
check("unrelated lines survive", 'gxResolution "1920x1080"' in text
      and 'realmList "logon.wowcircle.me"' in text)
check("restore without a Config.wtf fails quietly",
      not L.restore_config_cvars(os.path.join(tmp, "nope"), snap))

# ── what launch_wow puts into autologin.json ───────────────────────────────
wow2 = os.path.join(tmp, "game2")
os.makedirs(os.path.join(wow2, "WTF"))
shutil.copy2(exe, os.path.join(wow2, "Wow.exe"))
io.open(os.path.join(wow2, "WTF", "Config.wtf"), "w", encoding="utf-8").write(
    'SET farclip "777"\n')
popen_calls = []


class FakeProc:
    def wait(self):
        popen_calls.append("waited")
        return 0


L.subprocess.Popen = lambda *a, **k: (popen_calls.append(a), FakeProc())[1]
L.deploy_patch = lambda *a, **k: None
L.deploy_addon = lambda *a, **k: popen_calls.append(("addon", k))
seen_json = {}
real_write = L._write_autologin_json


def capture(wow_dir, char, realmlist, extra=None):
    seen_json.update(L._build_autologin_json(char, realmlist))
    seen_json.update(extra or {})
    real_write(wow_dir, char, realmlist, extra)


L._write_autologin_json = capture
launch_cfg = L._default_cfg()
launch_cfg.update({"wow_path": wow2, "anti_afk": True, "sync_friends": False,
                   "lfg": True, "characters": [
                       {"name": "", "account": "acc", "password": "pw",
                        "realm": "R", "realmlist": "logon.x",
                        "graphics": "minimal"},
                       {"name": "Twink", "account": "acc", "password": "pw",
                        "realm": "R", "realmlist": "logon.x"}]})
L.launch_wow(launch_cfg, launch_cfg["characters"][1])
time.sleep(1.5)                            # the restore thread
check("anti-AFK switch is passed to the DLL", seen_json.get("antiafk") == "1")
check("preset CVars are passed as cvar_ keys",
      seen_json.get("cvar_farclip") == "177"
      and seen_json.get("cvar_Sound_EnableAllSound") == "0")
check("the manager waits for the client to restore Config.wtf",
      "waited" in popen_calls)
check("addon flags are passed through", any(
    isinstance(c, tuple) and c[0] == "addon"
    and c[1].get("sync_friends") is False and c[1].get("lfg") is True
    for c in popen_calls))

seen_json.clear()
launch_cfg["anti_afk"] = False
launch_cfg["characters"][0]["graphics"] = ""
L.launch_wow(launch_cfg, launch_cfg["characters"][1])
check("no anti-AFK key when it is off", "antiafk" not in seen_json)
check("no cvar_ keys without a preset",
      not any(k.startswith("cvar_") for k in seen_json))

# ── Config.lua carries the new addon flags ────────────────────────────────
spec2 = importlib.util.spec_from_file_location("launcher2", os.path.abspath("launcher.py"))
L2 = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(L2)
os.makedirs(os.path.join(wow2, "Interface", "AddOns"), exist_ok=True)
L2.deploy_addon(wow2, True, True, characters=[], sync_friends=False, lfg=True)
conf_lua = io.open(os.path.join(wow2, "Interface", "AddOns", "WowManager",
                                "Config.lua"), encoding="utf-8").read()
check("Config.lua has syncFriends and lfg",
      "syncFriends = false" in conf_lua and "lfg = true" in conf_lua)

print()
bad = [n for n, v in ok if not v]
print("%d/%d passed" % (len(ok) - len(bad), len(ok)))
sys.exit(1 if bad else 0)
