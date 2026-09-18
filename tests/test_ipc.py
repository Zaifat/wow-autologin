# -*- coding: utf-8 -*-
"""Round-trip the single-instance IPC channel."""
import importlib.util, os, socket, tempfile, threading, time, sys

spec = importlib.util.spec_from_file_location("launcher", os.path.abspath("launcher.py"))
L = importlib.util.module_from_spec(spec)
spec.loader.exec_module(L)

tmp = tempfile.mkdtemp(prefix="wowmgr_ipc_")
L._config_dir = lambda: tmp
L._SINGLE_INSTANCE_PORT = 47931

seen = []
L._start_single_instance_listener(lambda: seen.append("SHOW"),
                                  lambda v: seen.append("LAUNCH:" + v))
time.sleep(0.2)

# 1) a legitimate SHOW from "another copy"
assert L._send_to_existing(L._MSG_SHOW)
# 2) a legitimate LAUNCH with a cyrillic name
assert L._send_to_existing(L._MSG_LAUNCH + "Тестоперсонаж".encode("utf-8"))
# 3) an unauthenticated caller trying to start the game
c = socket.create_connection(("127.0.0.1", L._SINGLE_INSTANCE_PORT), timeout=1)
c.sendall(L._MSG_LAUNCH + b"Evil")
c.shutdown(socket.SHUT_RDWR)
c.close()
time.sleep(0.5)

print("received:", seen)
ok = (seen == ["SHOW", "LAUNCH:Тестоперсонаж"])
print("PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
