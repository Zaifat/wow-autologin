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

# user-built presets
ucfg = {"characters": [{"name": "", "account": "a", "graphics": "my1"},
                       {"name": "Ch", "account": "a", "graphics": "my1"}],
        "graphics_presets": {"my1": {"name": "Ночной",
                                     "cvars": {"farclip": "300",
                                               "maxFPS": "45",
                                               "bogusCvar": "1"}}}}
check("a user preset resolves", L.effective_graphics(ucfg, ucfg["characters"][1])
      == "my1")
check("only known CVars are kept",
      L.preset_cvars(ucfg, "my1") == {"farclip": "300", "maxFPS": "45"})
check("built-in presets still resolve",
      L.preset_cvars(ucfg, "minimal") == L.GRAPHICS_PRESETS["minimal"])
check("an unknown preset falls back to none",
      L.effective_graphics({"characters": [{"name": "X", "account": "a",
                                            "graphics": "ghost"}]},
                           {"name": "X", "account": "a", "graphics": "ghost"})
      == "")
opts = dict(L.graphics_options(ucfg))
check("the picker lists built-ins and user presets",
      "my1" in opts and "minimal" in opts and opts["my1"] == "Ночной")
check("the character picker offers 'same as account'",
      L.graphics_options(ucfg, for_character=True)[0][0] == ""
      and L.graphics_options(ucfg, for_character=True)[1][0] == "none")
check("a new key never collides", L.new_preset_key(ucfg) == "my2")
L.drop_preset(ucfg, "my1")
check("deleting a preset clears it everywhere",
      not L.user_presets(ucfg)
      and all(not e.get("graphics") for e in ucfg["characters"]))
check("values are stored the way the client writes them",
      (L.gfx_value_str(1.0), L.gfx_value_str(0.75), L.gfx_value_str(30))
      == ("1", "0.75", "30"))
check("every builder setting is a real 3.3.5a CVar",
      all(c in {"farclip", "groundEffectDensity", "groundEffectDist",
                "environmentDetail", "particleDensity", "weatherDensity",
                "extShadowQuality", "spellEffectLevel", "detailDoodadAlpha",
                "projectedTextures", "maxFPS", "maxFPSBk",
                "Sound_EnableAllSound", "Sound_EnableMusic"}
          for c, _l, _k, _lo, _hi, _st, _d in L.GRAPHICS_SETTINGS))

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
launch_cfg["graphics_presets"] = {"my1": {"name": "Ночной",
                                          "cvars": {"farclip": "300"}}}
launch_cfg["characters"][0]["graphics"] = "my1"
L.launch_wow(launch_cfg, launch_cfg["characters"][1])
check("a user preset reaches the DLL", seen_json.get("cvar_farclip") == "300")
# screen settings travel through Config.wtf, not through the DLL
seen_json.clear()
launch_cfg["graphics_presets"] = {"scr": {"name": "Окно", "cvars": {
    "gxWindow": "1", "gxMaximize": "1", "gxResolution": "1600x900",
    "farclip": "300"}}}
launch_cfg["characters"][0]["graphics"] = "scr"
L.launch_wow(launch_cfg, launch_cfg["characters"][1])
check("screen CVars are not sent to the DLL",
      "cvar_gxResolution" not in seen_json and "cvar_gxWindow" not in seen_json)
check("...but the other CVars still are",
      seen_json.get("cvar_farclip") == "300")
written = io.open(os.path.join(wow2, "WTF", "Config.wtf"),
                  encoding="utf-8").read()
check("screen CVars are written into Config.wtf before launch",
      'SET gxResolution "1600x900"' in written
      and 'SET gxMaximize "1"' in written)
check("borderless is window + maximize",
      L.screen_mode_cvars("borderless") == {"gxWindow": "1",
                                            "gxMaximize": "1"}
      and L.screen_mode_of({"gxWindow": "1", "gxMaximize": "1"})
      == "borderless")
check("fullscreen round-trips",
      L.screen_mode_of(L.screen_mode_cvars("full")) == "full")
check("no screen keys means no mode", L.screen_mode_of({"farclip": "1"}) == "")
check("the resolution list is not empty and looks like WxH",
      all("x" in r for r in L.available_resolutions()))
launch_cfg["characters"][0]["graphics"] = ""
launch_cfg["graphics_presets"] = {}

seen_json.clear()
launch_cfg["anti_afk"] = False
launch_cfg["characters"][0]["graphics"] = ""
launch_cfg["graphics_presets"] = {}
L.launch_wow(launch_cfg, launch_cfg["characters"][1])
check("no anti-AFK key when it is off", "antiafk" not in seen_json)
check("no cvar_ keys without a preset",
      not any(k.startswith("cvar_") for k in seen_json))

# ── harvest: one launch per account, driven by the addon ──────────────────
client_alive = [0]


class HarvestApp:
    """Just enough of App for _harvest_worker."""
    cfg = None
    _harvest_stop = False
    logged = []

    def _harvest_log(self, line):
        self.logged.append(line)

    # the real waiting logic, so the test exercises it
    _wait_for_client_exit = L.App._wait_for_client_exit

    def _client_running(self):
        # "the client is up" for the first few polls of each account
        client_alive[0] -= 1
        return client_alive[0] > 0

    def __init__(self, cfg):
        self.cfg = cfg
        self.root = type("R", (), {"after": staticmethod(
            lambda _d, fn=None, *a: fn(*a) if fn else None)})()

    _refresh_ingame = lambda self: None
    _import_char_lists = lambda self, lists: None


harvest_cfg = L._default_cfg()
harvest_cfg.update({"wow_path": wow2, "characters": [
    {"name": "", "account": "acc", "password": "pw", "realm": "R",
     "realmlist": "logon.x"},
    {"name": "Один", "account": "acc", "password": "pw", "realm": "R"},
    {"name": "Два", "account": "acc", "password": "pw", "realm": "R"},
    {"name": "", "account": "empty-acc", "password": "pw", "realm": "R",
     "realmlist": "logon.x"}]})
L.normalize_roster(harvest_cfg)
launches = []


class HarvestProc:
    def __init__(self, alive=1):
        self.alive = alive
        self.killed = False

    def poll(self):
        self.alive -= 1
        return None if self.alive > 0 else 0

    def terminate(self):
        self.killed = True
        self.alive = 0


procs = []


def fake_launch(cfg, char, on_error=None, harvest_chars=None):
    launches.append((char.get("name") or char.get("account"), harvest_chars))
    client_alive[0] = 2
    procs.append(HarvestProc())
    return procs[-1]


L.launch_wow = fake_launch
addon_calls = []
L.deploy_addon = lambda *a, **k: addon_calls.append(k)
app = HarvestApp(harvest_cfg)
lines = []
L.App._harvest_worker(app, [(harvest_cfg["characters"][0],
                             harvest_cfg["characters"][1:3]),
                            (harvest_cfg["characters"][3], [])],
                      lines.append, lambda *a: None, lambda: None)
check("one launch per account", len(launches) == 2)
check("the run starts at the account's first character",
      launches[0][0] == "Один")
check("the addon gets the whole character list",
      launches[0][1] == ["Один", "Два"])
check("an account with no characters is visited too",
      launches[1][0] == "empty-acc" and launches[1][1] == [])
check("harvest mode is switched off afterwards",
      addon_calls and not addon_calls[-1].get("harvest_chars"))
check("the run is reported", any("acc" in ln for ln in lines))
check("the run is written to the harvest log",
      any("run start" in ln for ln in app.logged)
      and any("run end" in ln for ln in app.logged))


# stop button
launches.clear()
app._harvest_stop = True
L.App._harvest_worker(app, [(harvest_cfg["characters"][0],
                             harvest_cfg["characters"][1:3])],
                      lines.append, lambda *a: None, lambda: None)
check("stop prevents any launch", not launches)

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
check("harvest is off by default", "harvest = false" in conf_lua)
L2.deploy_addon(wow2, True, True, characters=[],
                harvest_chars=["Один", "Два"], harvest_wait=9)
conf_lua = io.open(os.path.join(wow2, "Interface", "AddOns", "WowManager",
                                "Config.lua"), encoding="utf-8").read()
check("harvest list reaches the addon",
      "harvest = true" in conf_lua and "harvestWait = 9" in conf_lua
      and '"Один", "Два"' in conf_lua)

print()
bad = [n for n, v in ok if not v]
print("%d/%d passed" % (len(ok) - len(bad), len(ok)))
sys.exit(1 if bad else 0)
