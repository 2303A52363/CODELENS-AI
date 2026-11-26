"""Per-language analysis. Each language has its OWN validator and (where meaningful) runner.
Diagnostic = {line, severity, name, message, kind}. Missing toolchains are reported, never faked."""
import os, re, shutil, subprocess, tempfile, time, signal, sqlite3
from html.parser import HTMLParser
import config
from services import analyzer, sandbox
try: import resource
except ImportError: resource = None

INSTALL = {"gcc": "Install MinGW-w64/MSYS2 (Windows) or `sudo apt install build-essential`, then reopen the terminal.",
           "java": "Install a JDK (e.g. Temurin 17+): `winget install EclipseAdoptium.Temurin.17.JDK`; make sure both `java` and `javac` work.",
           "node": "Install Node.js LTS from nodejs.org (`winget install OpenJS.NodeJS.LTS`)."}
def _have(*n): return all(shutil.which(x) for x in n)
def _sqlglot():
    try: import sqlglot; return True
    except ImportError: return False

LANGS = {  # id: (label, tools needed fn, can_run, isolation note)
 "python": ("Python", lambda: True, True, "audit-hook sandbox (or Docker)"),
 "c": ("C", lambda: _have("gcc"), True, "process limits only"), "cpp": ("C++", lambda: _have("g++"), True, "process limits only"),
 "java": ("Java", lambda: _have("java", "javac"), True, "process limits only"), "javascript": ("JavaScript", lambda: _have("node"), True, "process limits only"),
 "html": ("HTML", lambda: True, False, "validation only"), "css": ("CSS", lambda: True, False, "validation only"),
 "sql": ("SQL", lambda: _sqlglot(), True, "in-memory SQLite, restricted"),
}
def availability():
    out = []
    for k, (label, chk, run, iso) in LANGS.items():
        ok = chk(); hint = "" if ok else (INSTALL["gcc"] if k in ("c", "cpp") else INSTALL["java"] if k == "java" else INSTALL["node"] if k == "javascript" else "pip install sqlglot")
        out.append({"id": k, "label": label, "available": ok, "can_run": run, "isolation": iso, "install_hint": hint})
    return out
def require(lang):
    if lang not in LANGS: raise ValueError(f"Unsupported language '{lang}'.")
    if not LANGS[lang][1](): raise ValueError(f"{LANGS[lang][0]} tools are not installed on this machine. " + next(a["install_hint"] for a in availability() if a["id"] == lang))

def D(line, name, msg, sev="error", kind="Syntax Error"): return {"line": line, "severity": sev, "name": name, "message": msg, "kind": kind}

def _cmd(cmd, cwd, stdin="", timeout=None, as_limit=False):
    timeout = timeout or config.EXEC_TIMEOUT; start = time.perf_counter()
    def lim():
        if not resource: return
        resource.setrlimit(resource.RLIMIT_CPU, (int(timeout) + 2,) * 2); resource.setrlimit(resource.RLIMIT_FSIZE, (5_000_000,) * 2)
        resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
        if as_limit: resource.setrlimit(resource.RLIMIT_AS, (config.EXEC_MEMORY_MB * 1048576,) * 2)
    kw = {"preexec_fn": lim, "start_new_session": True} if os.name == "posix" else {}
    env = {**os.environ, "LC_ALL": "C"}
    p = subprocess.Popen(cmd, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env, **kw)
    to = False
    try: out, err = p.communicate(stdin or "", timeout=timeout)
    except subprocess.TimeoutExpired:
        to = True
        try: os.killpg(p.pid, signal.SIGKILL)
        except Exception: p.kill()
        out, err = p.communicate()
    return {"stdout": out[:20000], "stderr": err[:20000], "exit_code": p.returncode, "timed_out": to, "duration_ms": round((time.perf_counter() - start) * 1000, 1), "truncated": False}

GCC_RE = re.compile(r"^[^:\n]+:(\d+):(?:\d+:)?\s*(error|warning|fatal error):\s*(.*)$", re.M)
def _gcc(code, lang, run_it, stdin):
    exe = "gcc" if lang == "c" else "g++"; ext = "c" if lang == "c" else "cpp"
    with tempfile.TemporaryDirectory() as d:
        open(f"{d}/main.{ext}", "w").write(code)
        r = _cmd([exe, "-Wall", "-Wextra", "-o", "prog", f"main.{ext}"] + ([] if lang == "c" else ["-std=c++17"]), d, timeout=20)
        diags = [D(int(m[0]), "CompileError" if "error" in m[1] else "Warning", m[2], "error" if "error" in m[1] else "warning", "Syntax Error" if "error" in m[1] else "Warning") for m in GCC_RE.findall(r["stderr"])]
        if any(x["severity"] == "error" for x in diags) or r["exit_code"] != 0 and not diags:
            if not diags: diags = [D(None, "CompileError", r["stderr"][:300])]
            return diags, None
        if not run_it: return diags, None
        ex = _cmd(["./prog"], d, stdin, as_limit=True); return diags, ex

JAVAC_RE = re.compile(r"^[^:\n]+\.java:(\d+):\s*(error|warning):\s*(.*)$", re.M)
def _java(code, run_it, stdin):
    m = re.search(r"class\s+(\w+)[^{]*\{(?:(?!class\s).)*?static\s+void\s+main", code, re.S) or re.search(r"public\s+class\s+(\w+)", code)
    name = m.group(1) if m else "Main"
    with tempfile.TemporaryDirectory() as d:
        open(f"{d}/{name}.java", "w").write(code)
        r = _cmd(["javac", f"{name}.java"], d, timeout=30)
        diags = [D(int(a), "CompileError" if b == "error" else "Warning", c, b, "Syntax Error" if b == "error" else "Warning") for a, b, c in JAVAC_RE.findall(r["stderr"])]
        if r["exit_code"] != 0:
            return diags or [D(None, "CompileError", r["stderr"][:300])], None
        if not run_it: return diags, None
        return diags, _cmd(["java", "-Xmx128m", "-cp", d, name], d, stdin)

def _js(code, run_it, stdin):
    with tempfile.TemporaryDirectory() as d:
        open(f"{d}/main.js", "w").write(code)
        r = _cmd(["node", "--check", "main.js"], d, timeout=10)
        if r["exit_code"] != 0:
            ln = re.search(r"main\.js:(\d+)", r["stderr"]); msg = re.search(r"^(\w*Error): (.*)$", r["stderr"], re.M)
            return [D(int(ln.group(1)) if ln else None, msg.group(1) if msg else "SyntaxError", msg.group(2) if msg else r["stderr"][:200])], None
        diags = []
        for i, l in enumerate(code.splitlines(), 1):
            if re.search(r"[^=!]==[^=]", l) and not re.search(r"==\s*=", l): diags.append(D(i, "LooseEquality", "'==' does type coercion; prefer '==='.", "warning", "Code Quality"))
            if re.search(r"\bvar\s", l): diags.append(D(i, "VarUsage", "Prefer let/const over var.", "warning", "Code Quality"))
        return diags, (_cmd(["node", "main.js"], d, stdin) if run_it else None)

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
class _H(HTMLParser):
    def __init__(s): super().__init__(); s.stack, s.d, s.seen = [], [], set()
    def handle_starttag(s, tag, attrs):
        a = dict(attrs); s.seen.add(tag); ln = s.getpos()[0]
        if tag == "img" and "alt" not in a: s.d.append(D(ln, "MissingAlt", "<img> needs an alt attribute (accessibility).", "warning", "Accessibility"))
        if tag == "a" and "href" not in a: s.d.append(D(ln, "MissingHref", "<a> has no href attribute.", "warning", "Code Quality"))
        if tag == "html" and "lang" not in a: s.d.append(D(ln, "MissingLang", "<html> should declare lang.", "warning", "Accessibility"))
        if tag == "input" and a.get("type") not in ("submit", "button", "hidden") and not any(k in a for k in ("id", "aria-label")): s.d.append(D(ln, "UnlabelledInput", "<input> should have an id (for <label>) or aria-label.", "warning", "Accessibility"))
        if tag not in VOID: s.stack.append((tag, ln))
    def handle_startendtag(s, tag, attrs): s.handle_starttag(tag, attrs); (s.stack.pop() if tag not in VOID and s.stack and s.stack[-1][0] == tag else None)
    def handle_endtag(s, tag):
        ln = s.getpos()[0]
        if tag in VOID: return
        if not s.stack or tag not in [t for t, _ in s.stack]: s.d.append(D(ln, "UnexpectedClosingTag", f"</{tag}> has no matching opening tag.")); return
        while s.stack[-1][0] != tag:
            t, l = s.stack.pop(); s.d.append(D(l, "UnclosedTag", f"<{t}> opened here is not closed before </{tag}> (incorrect nesting or missing </{t}>)."))
        s.stack.pop()
def _html(code):
    h = _H()
    try: h.feed(code); h.close()
    except Exception as e: return [D(None, "ParseError", str(e))]
    d = h.d + [D(l, "UnclosedTag", f"<{t}> is never closed.") for t, l in h.stack]
    if "<!doctype" not in code.lower(): d.append(D(1, "MissingDoctype", "Add <!DOCTYPE html> at the top.", "warning", "Code Quality"))
    if "html" in h.seen and "title" not in h.seen: d.append(D(1, "MissingTitle", "Document has no <title>.", "warning", "Accessibility"))
    if "html" in h.seen and not ({"main", "header", "nav", "section", "article", "footer"} & h.seen): d.append(D(None, "NoSemanticTags", "Consider semantic elements (<header>, <main>, <nav>, <footer>).", "warning", "Accessibility"))
    return sorted(d, key=lambda x: x["line"] or 0)

CSS_PROPS = set("""align-content align-items align-self animation animation-delay animation-duration animation-name background background-attachment background-clip background-color background-image background-position background-repeat background-size border border-bottom border-bottom-color border-bottom-left-radius border-bottom-right-radius border-bottom-style border-bottom-width border-collapse border-color border-left border-radius border-right border-spacing border-style border-top border-top-left-radius border-top-right-radius border-width bottom box-shadow box-sizing clear color column-gap content cursor display filter flex flex-basis flex-direction flex-flow flex-grow flex-shrink flex-wrap float font font-family font-size font-style font-variant font-weight gap grid grid-area grid-column grid-gap grid-row grid-template grid-template-areas grid-template-columns grid-template-rows height justify-content justify-items left letter-spacing line-height list-style margin margin-bottom margin-left margin-right margin-top max-height max-width min-height min-width object-fit opacity order outline overflow overflow-x overflow-y padding padding-bottom padding-left padding-right padding-top place-items pointer-events position resize right row-gap text-align text-decoration text-overflow text-transform top transform transition transition-delay transition-duration transition-property transition-timing-function user-select vertical-align visibility white-space width word-break word-wrap z-index aspect-ratio inset backdrop-filter scroll-behavior text-shadow""".split())
def _css(code):
    d, depth, buf, bline, ln, sel_stack, decls = [], 0, "", 1, 1, [], [{}]
    clean = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), code, flags=re.S)
    def decl(txt, line, missing_semi):
        t = txt.strip()
        if not t: return
        parts = re.split(r"\n(?=\s*[\w-]+\s*:)", t)
        if len(parts) > 1:  # declarations on separate lines with no ';' between them
            off = 0
            for part in parts[:-1]:
                decl(part, line + off, True); off += part.count("\n") + 1
            decl(parts[-1], line + off, missing_semi); return
        if ":" not in t: d.append(D(line, "InvalidDeclaration", f"'{t[:40]}' is not a valid declaration (missing ':').")); return
        p, v = (x.strip() for x in t.split(":", 1)); pl = p.lower()
        if not v: d.append(D(line, "EmptyValue", f"Property '{p}' has no value."))
        if not (pl.startswith("--") or pl.startswith("-")) and pl not in CSS_PROPS and "@" not in p: d.append(D(line, "UnknownProperty", f"'{p}' is not a recognised CSS property (typo?).", "warning", "Code Quality"))
        if pl in decls[-1]: d.append(D(line, "DuplicateDeclaration", f"'{p}' is declared twice in this rule (first on line {decls[-1][pl]}).", "warning", "Code Quality"))
        decls[-1][pl] = line
        if missing_semi: d.append(D(line, "MissingSemicolon", f"Missing ';' after '{t[:40]}'."))
    i = 0
    for ch in clean + "\0":
        if ch == "\n": ln += 1
        if ch == "{":
            sel = buf.strip()
            if not sel: d.append(D(ln, "EmptySelector", "Rule has no selector."))
            depth += 1; sel_stack.append(ln); decls.append({}); buf = ""; bline = ln
        elif ch == ";": decl(buf, bline, False); buf = ""; bline = ln
        elif ch == "}":
            if depth == 0: d.append(D(ln, "UnmatchedBrace", "Extra '}' with no opening '{'."))
            else:
                if buf.strip() and ":" in buf: decl(buf, bline, True)
                elif buf.strip(): d.append(D(bline, "InvalidDeclaration", f"'{buf.strip()[:40]}' is not valid inside a rule."))
                depth -= 1; sel_stack.pop(); decls.pop()
            buf = ""; bline = ln
        else:
            if not buf.strip(): bline = ln
            buf += ch
    for l in sel_stack: d.append(D(l, "UnclosedBrace", "This '{' is never closed."))
    if buf.replace("\0", "").strip(): d.append(D(bline, "TrailingText", f"Text outside any rule: '{buf.strip()[:40]}'."))
    return d

def _sql(code, run_it):
    import sqlglot
    from sqlglot import exp
    from sqlglot.errors import ParseError
    d = []
    try: trees = [t for t in sqlglot.parse(code, read="sqlite") if t is not None]
    except ParseError as e:
        er = (e.errors or [{}])[0]; msg = er.get("description", str(e))
        if "Required keyword" in msg or "<class" in msg: msg = "Incomplete or malformed statement: a required part of the clause is missing (for example the column list after SELECT or a condition after WHERE)."
        return [D(er.get("line"), "SQLSyntaxError", msg[:240])], None
    for t in trees:
        for j in t.find_all(exp.Join):
            if not j.args.get("on") and not j.args.get("using") and not j.args.get("kind") == "CROSS" and not j.args.get("method"):
                d.append(D(None, "JoinWithoutCondition", "JOIN has no ON/USING condition (produces a cartesian product).", "warning", "Logical Error"))
        if isinstance(t, (exp.Update, exp.Delete)) and not t.args.get("where"): d.append(D(None, "MissingWhere", f"{type(t).__name__.upper()} without WHERE affects every row.", "warning", "Logical Error"))
        if isinstance(t, exp.Select) and any(isinstance(s, exp.Star) for s in t.expressions): d.append(D(None, "SelectStar", "SELECT * reads all columns; list only the columns you need.", "warning", "Performance"))
    if not run_it: return d, None
    return d, _sql_run(code)

def _sql_run(code):
    conn = sqlite3.connect(":memory:"); start = time.perf_counter(); out, err = [], ""
    def auth(act, a1, a2, db, src):
        if act in (sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH, sqlite3.SQLITE_PRAGMA): return sqlite3.SQLITE_DENY
        if act == sqlite3.SQLITE_FUNCTION and a2 == "load_extension": return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK
    conn.set_authorizer(auth); deadline = start + config.EXEC_TIMEOUT
    conn.set_progress_handler(lambda: 1 if time.perf_counter() > deadline else 0, 10000)
    stmt, sline, line, errline = "", 1, 0, None
    try:
        for l in code.splitlines():
            line += 1
            if not stmt.strip(): sline = line
            stmt += l + "\n"
            if sqlite3.complete_statement(stmt):
                errline = sline; cur = conn.execute(stmt)
                if cur.description: out.append(f"-- result of statement at line {sline}\n" + " | ".join(c[0] for c in cur.description) + "\n" + "\n".join(" | ".join(map(str, r)) for r in cur.fetchmany(100)))
                stmt = ""
        conn.commit()
    except sqlite3.Error as e: err = f"{type(e).__name__}: {e}\n(statement starting at line {errline})"
    finally: conn.close()
    return {"stdout": "\n\n".join(out), "stderr": err, "exit_code": 1 if err else 0, "timed_out": "interrupted" in err, "duration_ms": round((time.perf_counter() - start) * 1000, 1), "truncated": False, "_sql_line": errline if err else None}

def analyze(lang, code, stdin=""):
    """Returns diagnostics + optional execution dict. Python is handled by the Python pipeline in app.py."""
    require(lang); can_run = LANGS[lang][2]
    if lang in ("c", "cpp"): d, ex = _gcc(code, lang, True, stdin)
    elif lang == "java": d, ex = _java(code, True, stdin)
    elif lang == "javascript": d, ex = _js(code, True, stdin)
    elif lang == "html": d, ex = _html(code), None
    elif lang == "css": d, ex = _css(code), None
    elif lang == "sql": d, ex = _sql(code, True)
    err = next((x for x in d if x["severity"] == "error"), None); lines = code.splitlines(); first = err
    if err is None and ex and (ex["timed_out"] or ex["exit_code"] != 0):
        if ex["timed_out"]: err = {"line": None, "severity": "error", "name": "TimeLimitExceeded", "message": "Execution exceeded the time limit.", "kind": "Execution Error"}
        elif lang == "sql": err = D(ex.get("_sql_line"), "SQLRuntimeError", ex["stderr"].splitlines()[0], kind="Runtime Error")
        else:
            m = re.search(r"^(\w*(?:Error|Exception)): (.*)$", ex["stderr"], re.M); ln = re.search(r"(?:main\.js|\.java):(\d+)", ex["stderr"])
            name = m.group(1) if m else ("SegmentationFault" if ex["exit_code"] == -11 else "RuntimeError")
            err = D(int(ln.group(1)) if ln else None, name, (m.group(2) if m else ex["stderr"][:200] or f"Exit code {ex['exit_code']}"), kind="Runtime Error")
    if err: err = {"name": err["name"], "type": err["kind"], "line": err["line"], "code_line": lines[err["line"] - 1] if err["line"] and err["line"] <= len(lines) else "",
                   "message": err["message"], "source": f"{lang}-toolchain" if lang not in ("html", "css", "sql") else f"{lang}-validator", "line_reliable": err["line"] is not None}
    warnings = [{"line": x["line"], "code": x["name"], "message": x["message"], "kind": x["kind"]} for x in d if x is not first and x["severity"] in ("warning", "error")]
    if ex: ex.pop("_sql_line", None)
    return {"error": err, "warnings": warnings, "execution": ex}

def check(lang, code):
    """Validation used to verify AI corrections: returns (ok, message). Never runs for html/css beyond validation."""
    if lang == "python":
        e = analyzer.detect_syntax(code); return (e is None, "" if e is None else f"{e['name']} on line {e['line']}: {e['message']}")
    r = analyze(lang, code, "")
    if r["error"] and r["error"]["type"] in ("Syntax Error",): return False, f"{r['error']['name']} on line {r['error']['line']}: {r['error']['message']}"
    return True, ""
