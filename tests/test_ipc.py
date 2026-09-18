# -*- coding: utf-8 -*-
"""Round-trip the single-instance IPC channel, including the upgrade case:
an old (pre-1.5) manager in the tray holds the port but never acknowledges."""
import importlib.util, os, socket, tempfile, threading, time, sys

spec = importlib.util.spec_from_file_location("launcher", os.path.abspath("launcher.py"))
L = importlib.util.module_from_spec(spec)
spec.loader.exec_module(L)

tmp = tempfile.mkdtemp(prefix="wowmgr_ipc_")
L._config_dir = lambda: tmp
ok = []


def check(name, cond):
    ok.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name)


# ── nobody listening ───────────────────────────────────────────────────────
L._SINGLE_INSTANCE_PORT = 47933
check("no instance -> IPC_NONE", L._send_to_existing(L._MSG_SHOW) == L.IPC_NONE)

# ── a current instance ─────────────────────────────────────────────────────
L._SINGLE_INSTANCE_PORT = 47931
seen = []
L._start_single_instance_listener(lambda: seen.append("SHOW"),
                                  lambda v: seen.append("LAUNCH:" + v))
time.sleep(0.2)
check("SHOW acknowledged", L._send_to_existing(L._MSG_SHOW) == L.IPC_OK)
check("LAUNCH acknowledged",
      L._send_to_existing(L._MSG_LAUNCH + "Тестоперсонаж".encode("utf-8"))
      == L.IPC_OK)

# an unauthenticated caller trying to start the game gets nothing
c = socket.create_connection(("127.0.0.1", L._SINGLE_INSTANCE_PORT), timeout=1)
c.sendall(L._MSG_LAUNCH + b"Evil")
c.shutdown(socket.SHUT_WR)
c.settimeout(1.5)
try:
    reply = c.recv(16)
except OSError:
    reply = b""
c.close()
time.sleep(0.3)
check("unauthenticated caller gets no ack", reply == b"")
check("only the authenticated requests ran",
      seen == ["SHOW", "LAUNCH:Тестоперсонаж"])

# ── an old manager: accepts, reads, never answers ─────────────────────────
L._SINGLE_INSTANCE_PORT = 47932
old = socket.socket()
old.bind(("127.0.0.1", L._SINGLE_INSTANCE_PORT))
old.listen(4)


def old_manager():
    while True:
        conn, _ = old.accept()
        with conn:
            conn.recv(512)          # 1.4 behaviour: read, ignore, close


threading.Thread(target=old_manager, daemon=True).start()
time.sleep(0.2)
check("pre-1.5 instance -> IPC_STALE",
      L._send_to_existing(L._MSG_SHOW) == L.IPC_STALE)

print()
bad = [n for n, v in ok if not v]
print("%d/%d passed" % (len(ok) - len(bad), len(ok)))
sys.exit(1 if bad else 0)
