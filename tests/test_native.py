# -*- coding: utf-8 -*-
"""Compile and run the native C++ tests with the DLL's own MSVC toolchain.

Skipped when Visual Studio (vcvars32.bat) isn't installed.
"""
import glob
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ok = []


def check(name, cond):
    ok.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name)


vcvars = sorted(glob.glob(r"C:\Program Files*\Microsoft Visual Studio\*\*"
                          r"\VC\Auxiliary\Build\vcvars32.bat"))
if not vcvars:
    print("SKIP: Visual Studio C++ tools not found")
    raise SystemExit(0)

out_dir = tempfile.mkdtemp(prefix="wowmgr_native_")
exe = os.path.join(out_dir, "test_charlist.exe")
src = os.path.join(ROOT, "tests", "native", "test_charlist.cpp")
bat = os.path.join(out_dir, "build.bat")
with open(bat, "w") as fh:
    fh.write('@echo off\r\ncall "%s" >nul\r\n' % vcvars[-1])
    fh.write('cl /nologo /EHsc /std:c++17 /W4 /WX /Fe"%s" /Fo"%s\\\\" "%s" >"%s\\cl.log" 2>&1\r\n'
             % (exe, out_dir, src, out_dir))
r = subprocess.run(["cmd.exe", "/c", bat], capture_output=True)
if not os.path.isfile(exe):
    print(open(os.path.join(out_dir, "cl.log"), errors="replace").read())
check("native test compiles cleanly (/W4 /WX)", os.path.isfile(exe))
if not os.path.isfile(exe):
    sys.exit(1)

run = subprocess.run([exe, "--print"], capture_output=True)
if run.stderr:
    print(run.stderr.decode("utf-8", "replace"))
check("C++ self-checks pass", run.returncode == 0)

data = None
try:
    data = json.loads(run.stdout.decode("utf-8"))
except ValueError as e:
    print("bad json:", e)
check("output is valid JSON", data is not None)
if data:
    check("account and realm round-trip",
          data["account"] == "account_with_a_long_login_name"
          and data["realm"] == 'WoW Circle 3.3.5a x100 [MSK] "special"')
    check("every row made it", len(data["chars"]) == 11)
    check("Cyrillic name intact", data["chars"][0]["name"] == "Зайфат")
    check("widest numbers intact", data["chars"][0]["level"] == 255
          and data["chars"][0]["gender"] == 255)
    check("quotes, backslash and tab survive",
          data["chars"][10]["name"] == 'Quote"Back\\slash\ttab')
    check("huge timestamp intact", data["at"] == 18446744073709551615)

print()
bad = [n for n, v in ok if not v]
print("%d/%d passed" % (len(ok) - len(bad), len(ok)))
sys.exit(1 if bad else 0)
