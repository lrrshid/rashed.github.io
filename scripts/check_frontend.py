"""Frontend checks without a browser or Node.js:
  1. every ES module compiles (V8 through mini-racer; module syntax is rewritten to plain script, nothing runs);
  2. every imported name is exported by the module it comes from;
  3. every literal t('key') label exists in English (js/labels*.js) and in Arabic (js/i18n/ar/*.js).
Run from the project folder:  .venv\\Scripts\\python.exe scripts\\check_frontend.py   (exit code 1 on any problem)"""
from __future__ import annotations

import json
import pathlib
import re
import sys

from py_mini_racer import MiniRacer

ROOT = pathlib.Path(__file__).resolve().parents[1] / "frontend" / "js"
IMPORT_RE = re.compile(r"^import\s+([\s\S]*?)\s+from\s+'([^']+)';", re.M)
ctx = MiniRacer()
problems = 0


def report(message: str) -> None:
    global problems
    problems += 1
    print(message)


# ---- 1 and 2: syntax and imports
exports: dict[pathlib.Path, set[str]] = {}
imports = []
for path in sorted(ROOT.rglob("*.js")):
    src = path.read_text(encoding="utf-8")
    names = set(re.findall(r"^export\s+(?:async\s+)?(?:function|const|let|class)\s+([A-Za-z_$][\w$]*)", src, re.M))
    for group in re.findall(r"^export\s*\{([^}]*)\}", src, re.M):
        names |= {n.strip().split(" as ")[-1] for n in group.split(",") if n.strip()}
    if re.search(r"^export\s+default", src, re.M):
        names.add("default")
    exports[path.resolve()] = names
    imports += [(path, spec, target) for spec, target in IMPORT_RE.findall(src)]
    code = IMPORT_RE.sub("", src)
    code = re.sub(r"^export\s+default\s+", "const __default = ", code, flags=re.M)
    code = re.sub(r"^export\s+(?=(async\s+)?function|const|let|class)", "", code, flags=re.M)
    code = re.sub(r"^export\s*\{[^}]*\};?", "", code, flags=re.M)
    try:
        ctx.eval(f"new Function({json.dumps(code)})")
    except Exception as exc:  # noqa: BLE001 - any compile error is reported
        report(f"SYNTAX {path.relative_to(ROOT)}: {str(exc).splitlines()[0][:300]}")

for path, spec, target in imports:
    module = (path.parent / target).resolve()
    if module not in exports:
        report(f"MISSING MODULE {path.relative_to(ROOT)} -> {target}")
        continue
    wanted = []
    spec = spec.strip()
    if re.match(r"^[A-Za-z_$][\w$]*\s*(,|$)", spec):
        wanted.append("default")
    brace = re.search(r"\{([^}]*)\}", spec)
    if brace:
        wanted += [n.strip().split(" as ")[0].strip() for n in brace.group(1).split(",") if n.strip()]
    for name in wanted:
        if name not in exports[module]:
            report(f"MISSING EXPORT {path.relative_to(ROOT)} imports {name} from {target}")


# ---- 3: labels
def load_default(path: pathlib.Path) -> dict:
    src = path.read_text(encoding="utf-8")
    body = src[src.index("export default") + len("export default"):].strip().rstrip(";")
    return json.loads(ctx.eval(f"JSON.stringify({body})"))


labels = (ROOT / "labels.js").read_text(encoding="utf-8")
EN = json.loads(ctx.eval("JSON.stringify(" + labels[labels.index("const EN = ") + 11:labels.index("\n};\n") + 2] + ")"))
for extra in sorted(ROOT.glob("labels-*.js")):
    EN.update(load_default(extra))
AR: dict = {}
for path in sorted((ROOT / "i18n" / "ar").glob("*.js")):
    AR.update(load_default(path))


def has(d: dict, key: str) -> bool:
    node = d
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return False
        node = node[part]
    return True


used = set()
for path in ROOT.rglob("*.js"):
    used |= set(re.findall(r"\bt\('([A-Za-z0-9_.]+)'", path.read_text(encoding="utf-8")))
for key in sorted(used):
    if not has(EN, key):
        report(f"LABEL missing in English: {key}")
    elif not has(AR, key):
        report(f"LABEL missing in Arabic: {key}")

print(f"{len(exports)} modules, {len(used)} label keys checked; problems: {problems}")
sys.exit(1 if problems else 0)
