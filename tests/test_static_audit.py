# -*- coding: utf-8 -*-
"""Static audit passes over launcher.py that pyflakes doesn't do."""
import ast, io, sys, collections

src = io.open('launcher.py', encoding='utf-8').read()
tree = ast.parse(src)
problems = []

# ── duplicate keys in any dict literal ─────────────────────────────────────
for node in ast.walk(tree):
    if isinstance(node, ast.Dict):
        keys = [k.value for k in node.keys
                if isinstance(k, ast.Constant) and isinstance(k.value, str)]
        dupes = [k for k, n in collections.Counter(keys).items() if n > 1]
        for d in dupes:
            problems.append("dup dict key line %d: %r" % (node.lineno, d[:60]))

# ── functions defined but never referenced anywhere ────────────────────────
defined = {}
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef):
        defined.setdefault(node.name, node.lineno)
used = collections.Counter()
for node in ast.walk(tree):
    if isinstance(node, ast.Name):
        used[node.id] += 1
    elif isinstance(node, ast.Attribute):
        used[node.attr] += 1
for name, line in sorted(defined.items(), key=lambda kv: kv[1]):
    if name.startswith("__"):
        continue
    if used[name] == 0:
        problems.append("unreferenced function line %d: %s" % (line, name))

# ── bare except / except Exception: pass in new code is worth eyeballing ───
broad = 0
for node in ast.walk(tree):
    if isinstance(node, ast.ExceptHandler) and node.type is None:
        problems.append("bare except at line %d" % node.lineno)
    if isinstance(node, ast.ExceptHandler):
        broad += 1

# ── mutable default arguments ──────────────────────────────────────────────
for node in ast.walk(tree):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        for d in node.args.defaults + [x for x in node.args.kw_defaults if x]:
            if isinstance(d, (ast.List, ast.Dict, ast.Set)):
                problems.append("mutable default at line %d: %s"
                                % (node.lineno, node.name))

# ── every t("...") literal should resolve, i.e. exist in _EN or be new ─────
# (informational: report Russian literals passed to t() that _EN lacks)
en_keys = set()
for node in ast.walk(tree):
    if isinstance(node, ast.Assign):
        for tgt in node.targets:
            if isinstance(tgt, ast.Name) and tgt.id == "_EN":
                for k in node.value.keys:
                    if isinstance(k, ast.Constant):
                        en_keys.add(k.value)
missing = []
for node in ast.walk(tree):
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == "t" and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)):
        val = node.args[0].value
        if any("Ѐ" <= ch <= "ӿ" for ch in val) and val not in en_keys:
            missing.append((node.lineno, val))

print("handlers catching exceptions: %d" % broad)
if missing:
    print("\n-- Russian strings with no English translation (%d) --" % len(missing))
    for line, val in missing:
        print("  line %d: %s" % (line, val.replace("\n", " / ")[:80]))
if problems:
    print("\n-- problems (%d) --" % len(problems))
    for x in problems:
        print("  " + x)
    sys.exit(1)
print("\nno structural problems found")
