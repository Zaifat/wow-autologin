# -*- coding: utf-8 -*-
"""Smoke-test the new features: master password, weekly fields, realm probe,
addon deployment."""
import importlib.util, io, os, socket, sys, tempfile, threading, time

spec = importlib.util.spec_from_file_location("launcher", os.path.abspath("launcher.py"))
L = importlib.util.module_from_spec(spec)
spec.loader.exec_module(L)

tmp = tempfile.mkdtemp(prefix="wowmgr_f_")
ok = []


def check(name, cond):
    ok.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name)


# ── feature 9: master password ─────────────────────────────────────────────
salt = os.urandom(16)
key = L.derive_master_key("hunter22", salt)
L.set_master_key(key)
blob = L.encrypt_secret("s3cret-пароль", "master")
check("master blob is prefixed", blob.startswith("enc:m1:"))
check("master round-trip", L.decrypt_secret(blob) == "s3cret-пароль")
check("already-encrypted value is left alone",
      L.encrypt_secret(blob, "master") == blob)

# a different password must not open it
wrong = L.derive_master_key("hunter23", salt)
check("verifier rejects the wrong password",
      L.master_verifier(wrong) != L.master_verifier(key))
L.set_master_key(wrong)
check("wrong key fails to decrypt", L.decrypt_secret(blob) == "")
L.set_master_key(key)

# tampering must be caught by the MAC
import base64 as _b64
raw = bytearray(_b64.b64decode(blob[len("enc:m1:"):]))
raw[-1] ^= 0xFF
tampered = "enc:m1:" + _b64.b64encode(bytes(raw)).decode()
check("tampered ciphertext rejected", L.decrypt_secret(tampered) == "")

# full config round-trip in master mode
L.CONFIG_FILE = os.path.join(tmp, "characters.json")
cfg = L._default_cfg()
cfg["secret_mode"] = "master"
cfg["master_salt"] = _b64.b64encode(salt).decode()
cfg["master_check"] = L.master_verifier(key)
cfg["characters"] = [{"name": "Тест", "account": "acc", "password": "pw123",
                      "totp_secret": "JBSWY3DPEHPK3PXP", "class": "Маг",
                      "realm": "R", "realmlist": "logon.x"}]
L.save_cfg(cfg)
on_disk = io.open(L.CONFIG_FILE, encoding="utf-8").read()
check("password is not on disk in the clear", "pw123" not in on_disk)
check("2FA secret is not on disk in the clear", "JBSWY3DPEHPK3PXP" not in on_disk)
raw_cfg = L.load_cfg(decrypt=False)
check("load(decrypt=False) keeps ciphertext",
      raw_cfg["characters"][0]["password"].startswith("enc:m1:"))
check("cfg_has_encrypted_secrets sees it", L.cfg_has_encrypted_secrets(raw_cfg))
L.decrypt_cfg_secrets(raw_cfg)
check("decrypt_cfg_secrets restores plaintext",
      raw_cfg["characters"][0]["password"] == "pw123")

# saving while locked must not double-encrypt
L.set_master_key(None)
locked = L.load_cfg(decrypt=False)
L.save_cfg(locked)
L.set_master_key(key)
reopened = L.load_cfg()
check("save while locked preserves secrets",
      reopened["characters"][0]["password"] == "pw123")

# migration from the old boolean
old_cfg = {"encrypt_secrets": False, "characters": []}
check("legacy false -> plain", L.secret_mode(old_cfg) == "plain")
check("legacy true -> dpapi", L.secret_mode({"encrypt_secrets": True}) == "dpapi")

# ── feature 2: weekly progress formatting ─────────────────────────────────
rec = {"name": "Тест", "gold": 12345678, "played": 360000,
       "dailyDone": 7, "dailyMax": 25, "dailyResetAt": time.time() + 5 * 3600,
       "questsDone": 2, "questsTotal": 18, "arenaGames": 7,
       "arenaTeams": [{"size": 2, "rating": 1580, "played": 10, "mine": 7},
                      {"size": 3, "rating": 1490, "played": 4, "mine": 4}]}
check("dailies short form", L._ig_display(rec, "dailyDone") == "7 / 25")
long_daily = L._ig_display(rec, "dailyDone", long=True)
check("dailies long form has the reset timer",
      long_daily.startswith("7 / 25") and "4" in long_daily)
check("quests form", L._ig_display(rec, "questsDone") == "2 / 18")
check("gold still formats", "g" in L._ig_display(rec, "gold").lower()
      or L._ig_display(rec, "gold") != "")

L.INGAME.clear()
L.INGAME["тест"] = rec
lines = L.card_lines({"name": "Тест"}, L.CARD_ORDER)
joined = "\n".join(lines)
check("card lists arena teams", "2x2" in joined and "1580" in joined)
check("card lists dailies", "7 / 25" in joined)
check("weekly fields offered as card fields",
      "dailyDone" in L.available_card_fields()
      and "arenaTeams" in L.available_card_fields())
cols = L.available_columns()
check("weekly fields offered as columns",
      "dailyDone" in cols and "arenaGames" in cols and "questsDone" in cols)
check("composite building blocks are not columns",
      "dailyMax" not in cols and "questsTotal" not in cols
      and "dailyResetAt" not in cols and "arenaTeams" not in cols)
check("the realm ping is gone", not hasattr(L, "probe_realm")
      and "status" not in cols)

# ── feature 1: addon config carries the current account ───────────────────
wow = os.path.join(tmp, "wow")
os.makedirs(os.path.join(wow, "Interface", "AddOns"), exist_ok=True)
L.deploy_addon(wow, True, show_minimap=True,
               characters=[{"name": "Тест", "account": "acc", "class": "Маг"},
                           {"name": "", "account": "other"}],
               hover_card=True, card_fields=L.CARD_ORDER, card_labels={},
               current_account="acc")
conf = io.open(os.path.join(wow, "Interface", "AddOns", "WowManager",
                            "Config.lua"), encoding="utf-8").read()
check("addon config names the current account", 'currentAccount = "acc"' in conf)
check("addon config still lists entries", '"Тест"' in conf and '"other"' in conf)
check("Core.lua deployed",
      os.path.isfile(os.path.join(wow, "Interface", "AddOns", "WowManager",
                                  "Core.lua")))

print()
bad = [n for n, v in ok if not v]
print("%d/%d passed" % (len(ok) - len(bad), len(ok)))
sys.exit(1 if bad else 0)
