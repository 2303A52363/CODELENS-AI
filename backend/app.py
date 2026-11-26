import io, json, os, statistics
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import config
from services import sandbox, analyzer, complexity, quality, ai, db, report, languages
from nlp import intent as nlp_intent

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 200_000
CORS(app, origins=[config.CORS_ORIGIN])
EXT = {"python": ".py", "c": ".c", "cpp": ".cpp", "java": ".java", "javascript": ".js", "html": ".html", "css": ".css", "sql": ".sql"}

class BadInput(Exception): pass
def _code(d):
    code = (d or {}).get("code", "")
    if not isinstance(code, str) or not code.strip(): raise BadInput("Code is empty. Write or paste some code first.")
    if len(code.encode()) > config.MAX_CODE_BYTES: raise BadInput(f"Code is too large (max {config.MAX_CODE_BYTES} bytes).")
    if "\x00" in code: raise BadInput("Code contains invalid characters.")
    return code
def _lang(d):
    lang = (d or {}).get("language", "python")
    languages.require(lang)  # raises ValueError with install hint if the toolchain is missing
    return lang
@app.errorhandler(BadInput)
def bad(e): return jsonify(error=str(e)), 400
@app.errorhandler(ValueError)
def bad2(e): return jsonify(error=str(e)), 400
@app.errorhandler(413)
def big(e): return jsonify(error="Request too large."), 413
@app.errorhandler(Exception)
def boom(e):
    app.logger.exception("unhandled"); return jsonify(error="Internal error. Please try again."), 500

def _error_from(code, ex):
    if ex["timed_out"]: return analyzer.timeout_error(code)
    if ex.get("sandbox_error"): return None
    if ex["exit_code"] != 0: return analyzer.parse_traceback(ex["stderr"], code)
    return None

NA_NOTE = {"html": "HTML is markup, so Big-O does not apply.", "css": "CSS is a stylesheet, so Big-O does not apply.",
           "sql": "SQL cost depends on the database engine, indexes, the execution plan and data size, so no single Big-O is given."}
def _no_complexity(lang):
    return {"time": "N/A", "space": "N/A", "time_key": None, "space_key": None, "confidence": "not available",
            "explanation": NA_NOTE.get(lang, "Automatic Big-O estimation is implemented for Python only. Ask the assistant for an AI estimate (it will be labelled as an estimate)."),
            "space_explanation": "", "limitations": ["Static complexity analysis is not implemented for this language."]}

def _run(lang, code, stdin=""):
    """Execution dict, or None when not runnable / failed to compile."""
    if lang == "python": return None if analyzer.detect_syntax(code) else sandbox.run(code, stdin)
    return languages.analyze(lang, code, stdin)["execution"]

def _analysis(code, lang, stdin=""):
    if lang == "python":
        syn = analyzer.detect_syntax(code)
        ex = None if syn else sandbox.run(code, stdin)
        err = syn or _error_from(code, ex)
        if syn: err["suggestions"] = analyzer.syntax_hint(code, syn)
        res = {"execution": ex, "error": err, "warnings": analyzer.run_ruff(code) if not syn else [], "logic_hints": analyzer.logic_hints(code)}
        if not syn:
            res["complexity"] = complexity.analyze(code); res["quality"] = quality.score(code, res["warnings"] + res["logic_hints"])
        return res
    r = languages.analyze(lang, code, stdin)
    return {**r, "logic_hints": [], "complexity": _no_complexity(lang), "quality": None}

def _validate(lang, code, stdin=""):
    """Verification gate for AI-generated code. 'verified' only when the real toolchain accepts it."""
    if lang == "python":
        e = analyzer.detect_syntax(code)
        if e: return {"verified": False, "message": f"{e['name']} on line {e['line']}: {e['message']}", "method": "python-ast"}
        ex = sandbox.run(code, stdin)
        if ex["timed_out"]: return {"verified": False, "message": "Timed out when run.", "method": "sandbox run"}
        if ex["exit_code"] != 0:
            er = analyzer.parse_traceback(ex["stderr"], code) or {}
            return {"verified": False, "message": f"{er.get('name')} on line {er.get('line')}: {er.get('message')}", "method": "sandbox run"}
        return {"verified": True, "message": "Parses and runs without errors on the provided input. This does not prove the logic is correct.", "method": "python-ast + sandbox run"}
    r = languages.analyze(lang, code, stdin)
    if r["error"]: return {"verified": False, "message": f"{r['error']['name']} on line {r['error']['line']}: {r['error']['message']}", "method": f"{lang} toolchain"}
    how = {"html": "HTML validator", "css": "CSS validator", "sql": "sqlglot parser + in-memory SQLite run"}.get(lang, f"{lang} compile/run")
    return {"verified": True, "message": "Passes validation (" + how + "). This does not prove the logic is correct.", "method": how}

def _corrected(code, lang, err, stdin=""):
    out = ai.corrected_code(code, err, lang)
    if not out.get("ai"): return out
    v = _validate(lang, out["corrected_code"], stdin)
    if not v["verified"]:  # one automatic retry that feeds the failure back to Gemini
        out2 = ai.corrected_code(code, err, lang, previous_failure=v["message"])
        if out2.get("ai"):
            v2 = _validate(lang, out2["corrected_code"], stdin)
            out, v = (out2, v2) if v2["verified"] else (out2, v2)
    out["validation"] = v
    out["disclaimer"] = ("Verified by the toolchain. " if v["verified"] else "NOT VERIFIED: the suggestion failed validation. ") + "AI-generated suggestions should always be tested. Your original code was not changed."
    return out

def _time(lang, code, stdin):
    runs = [_run(lang, code, stdin) for _ in range(3)]
    if any(r is None or r["exit_code"] != 0 or r["timed_out"] for r in runs): return None, runs[0]
    return statistics.median(r["duration_ms"] for r in runs), runs[0]

def _optimize(code, lang, stdin):
    syn = _analysis(code, lang, stdin)
    if syn["error"] and syn["error"]["type"] == "Syntax Error": raise BadInput("Fix the syntax error before optimizing.")
    orig_c = syn.get("complexity") or _no_complexity(lang)
    res = ai.optimize(code, lang); res["original_complexity"] = orig_c
    if not res.get("ai"):
        res["static_findings"] = [{"line": h["line"], "problem": h["message"]} for h in syn.get("logic_hints", [])] + \
            [{"line": w["line"], "problem": w["message"]} for w in syn.get("warnings", []) if w.get("kind") in ("Performance", None) or lang != "python"][:6]
        return res
    new = res["optimized_code"]; v = _validate(lang, new, stdin); res["validation"] = v
    if not v["verified"]:
        res["verdict"] = "The suggested code failed validation, so no comparison was made. Do not use it as-is."; return res
    res["optimized_complexity"] = complexity.analyze(new) if lang == "python" else _no_complexity(lang)
    t0, r0 = _time(lang, code, stdin); t1, r1 = _time(lang, new, stdin)
    runnable = lang in ("python", "c", "cpp", "java", "javascript", "sql")
    same = runnable and t0 is not None and t1 is not None and r0["stdout"] == r1["stdout"]
    res["measured"] = {"original_ms": t0, "optimized_ms": t1, "same_output": same} if runnable else None
    ok, nk = orig_c.get("time_key"), res["optimized_complexity"].get("time_key")
    better = ok is not None and nk is not None and complexity.better(nk, ok)
    if not runnable: res["verdict"] = "Validated structurally; behaviour cannot be compared automatically for this language."
    elif not same: res["verdict"] = "Could not verify: outputs differ or a version failed. Do not assume the optimized code is equivalent."
    elif better: res["verdict"] = f"Estimated complexity improved ({orig_c['time']} -> {res['optimized_complexity']['time']}); outputs match."
    elif t1 < t0 * 0.8: res["verdict"] = f"Measured faster on this input ({t0}ms -> {t1}ms) with the same estimated complexity. Small inputs can be noisy."
    else: res["verdict"] = "No measurable improvement was shown; the changes may only improve readability."
    return res

@app.get("/api/health")
def health():
    nlp_ok = True
    try: nlp_intent._model()
    except Exception: nlp_ok = False
    return jsonify(ok=True, gemini_configured=ai.available(), gemini_model=config.GEMINI_MODEL, mongo=db.ping(), sandbox=config.SANDBOX_MODE, nlp_loaded=nlp_ok)
@app.get("/api/languages")
def langs(): return jsonify(languages=languages.availability())
@app.get("/api/nlp/metrics")
def nlp_metrics():
    p = os.path.join(os.path.dirname(nlp_intent.__file__), "metrics.json")
    return jsonify(json.load(open(p))) if os.path.exists(p) else (jsonify(error="Run `python -m nlp.train` first."), 404)
@app.post("/api/nlp/classify")
def nlp_classify():
    t = ((request.get_json(silent=True) or {}).get("text") or "").strip()
    if not t: raise BadInput("Text is empty.")
    return jsonify(nlp_intent.classify(t[:500]))
@app.post("/api/run")
def run():
    d = request.get_json(silent=True) or {}
    code = _code(d)
    lang = _lang(d)
    stdin = d.get("stdin", "")
    res = _analysis(code, lang, stdin)
    explanation = None
    if res["error"]:
        explanation = analyzer.kb_explanation(res["error"]["name"])
        explanation["ai"] = False
        explanation["ai_note"] = (
            "Built-in explanation displayed immediately. "
            "Use the chatbot when you need additional AI help.")
    res.update(language=lang,code=code,explanation=explanation)
    res["history_id"] = db.save({"code": code,"language": lang,"error": res["error"],"quality": res.get("quality"),"complexity": res.get("complexity")})
    res["history_saved"] = res["history_id"] is not None
    return jsonify(res)

@app.post("/api/corrected-code")
def corrected():
    d = request.get_json(silent=True); code = _code(d); lang = _lang(d)
    err = d.get("error") or _analysis(code, lang, d.get("stdin", ""))["error"] or {"name": "NoErrorDetected", "message": "No error detected; improve if possible."}
    return jsonify(_corrected(code, lang, err, d.get("stdin", "")))

@app.post("/api/tests")
def tests():
    d = request.get_json(silent=True); code = _code(d); lang = _lang(d); out = []
    if lang in ("html", "css"): raise BadInput("Test cases are not applicable to HTML/CSS.")
    for i, t in enumerate((d.get("cases") or [])[:20]):
        ex = _run(lang, code, t.get("input", ""))
        if ex is None: raise BadInput("Fix the compile/syntax error before running test cases.")
        got = ex["stdout"].strip()
        out.append({"case": i + 1, "input": t.get("input", ""), "expected": t.get("expected", ""), "actual": got,
                    "passed": ex["exit_code"] == 0 and not ex["timed_out"] and got == str(t.get("expected", "")).strip(),
                    "timed_out": ex["timed_out"], "stderr": ex["stderr"][-300:]})
    return jsonify(results=out, passed=sum(o["passed"] for o in out), total=len(out))

@app.post("/api/generate-tests")
def gen_tests():
    d = request.get_json(silent=True); code = _code(d); lang = _lang(d)
    if lang in ("html", "css"): raise BadInput("Test generation is not applicable to HTML/CSS.")
    return jsonify(_gen_tests(code, lang))
def _gen_tests(code, lang):
    out = ai.generate_tests(code, lang)
    for c in out.get("cases", []):  # record what the program ACTUALLY prints; this is not a claim of correctness
        ex = _run(lang, code, str(c.get("input", "")))
        c["actual_output"] = (ex["stdout"].strip() if ex and ex["exit_code"] == 0 else (f"(error: {ex['stderr'].strip()[-120:]})" if ex else "(did not run)"))
    out["note"] = "Inputs are AI-suggested. 'actual_output' is what your program printed; write the expected value yourself to check correctness."
    return out

@app.post("/api/optimize")
def optimize():
    d = request.get_json(silent=True); code = _code(d); lang = _lang(d)
    if lang in ("html", "css"): raise BadInput("Optimization comparison is available for programming languages and SQL.")
    return jsonify(_optimize(code, lang, d.get("stdin", "")))

def _facts(a, lang):
    f = []
    e = a.get("error")
    if e: f.append(f"Error: {e['name']} ({e['type']}) at line {e.get('line')}: {e.get('message')}. Line text: {e.get('code_line')!r}. Suggestions: {e.get('suggestions') or 'none'}")
    for w in a.get("warnings", [])[:6]: f.append(f"Warning line {w['line']}: {w['message']}")
    for h in a.get("logic_hints", [])[:6]: f.append(f"Logic hint line {h['line']}: {h['message']}")
    c = a.get("complexity")
    if c and c.get("time_key") is not None: f.append(f"Estimated complexity: time {c['time']}, space {c['space']}")
    return "\n".join(f) if f else "No errors or warnings found by static analysis/execution."

def _local_explain(a):
    e = a.get("error")
    if not e: return None
    x = analyzer.kb_explanation(e["name"]); steps = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(x["steps"]))
    sug = ("\n" + "\n".join(e["suggestions"])) if e.get("suggestions") else ""
    return f"**{e['name']}** ({e['type']}) on line {e.get('line')}: {e.get('message')}\n\n{x['what']} {x['why']}{sug}\n\n{steps}"

def _fence(code, lang): return f"```{lang}\n{code}\n```"

@app.post("/api/chat")
def chat():
    d = request.get_json(silent=True) or {}
    msg = str(d.get("message", "")).strip()
    if not msg: raise BadInput("Type a question first.")
    lang = _lang(d); code = (d.get("code") or "")[:config.MAX_CODE_BYTES]; history = d.get("history") or []; stdin = d.get("stdin", "")
    nlp = nlp_intent.classify(msg[:500]); it = nlp["intent"]; line = nlp.get("line")
    base = {"intent": nlp, "action": None, "ai": False, "reply": None, "error": None}
    if not code.strip() and it not in ("general_question",):
        return jsonify({**base, "reply": "There is no code in the editor yet. Paste some code and ask again."})
    a = _analysis(code, lang, stdin) if it in ("explain_error", "debug_code", "correct_code", "explain_complexity", "optimize_code") and code.strip() else {}
    facts = _facts(a, lang) if a else ""
    focus = f"\n(The student refers to line {line}: {code.splitlines()[line - 1]!r})" if line and code and line <= len(code.splitlines()) else ""
    if it == "correct_code":
        if lang in ("html", "css") and not a.get("error") and not a.get("warnings"): return jsonify({**base, "reply": "No problems were found, so there is nothing to correct."})
        r = _corrected(code, lang, a.get("error") or {"name": "ImproveCode", "message": "No hard error; fix warnings: " + facts}, stdin)
        if not r.get("ai"): return jsonify({**base, "error": r.get("error"), "reply": (_local_explain(a) or "") + "\n\nA complete corrected program needs Gemini, which is unavailable right now." if a.get("error") else None})
        v = r["validation"]
        txt = ("✅ **Verified**: " if v["verified"] else "⚠️ **Not verified**: ") + v["message"] + "\n\n" + _fence(r["corrected_code"], lang) + "\n\n" + "\n".join(f"- {c}" for c in r.get("changes", []))
        return jsonify({**base, "ai": True, "reply": txt, "action": {"type": "corrected_code", "code": r["corrected_code"], "verified": v["verified"]}})
    if it == "optimize_code":
        if lang in ("html", "css"): return jsonify({**base, "reply": "The optimizer compares runnable code and SQL. For HTML/CSS use the Errors tab for validation suggestions."})
        r = _optimize(code, lang, stdin)
        if not r.get("ai"): return jsonify({**base, "error": r.get("error"), "reply": "Static findings:\n" + "\n".join(f"- {f['problem']}" for f in r.get("static_findings", [])) if r.get("static_findings") else None})
        txt = r.get("summary", "") + "\n\n**Verdict:** " + r.get("verdict", "") + ("\n\n" + _fence(r["optimized_code"], lang) if r.get("validation", {}).get("verified") else "")
        return jsonify({**base, "ai": True, "reply": txt, "action": {"type": "optimized_code", "code": r["optimized_code"], "verified": r.get("validation", {}).get("verified", False)}})
    if it == "generate_tests":
        if lang in ("html", "css"): return jsonify({**base, "reply": "Test cases do not apply to HTML/CSS."})
        r = _gen_tests(code, lang)
        if not r.get("ai"): return jsonify({**base, "error": r.get("error")})
        txt = "\n".join(f"{i + 1}. **{c.get('category')}** – {c.get('description')}\n   input: `{str(c.get('input')).strip()[:60]}` → your program printed: `{c.get('actual_output', '')[:60]}`" for i, c in enumerate(r["cases"])) + "\n\n" + r["note"]
        return jsonify({**base, "ai": True, "reply": txt, "action": {"type": "tests", "cases": r["cases"]}})
    if it == "explain_complexity" and lang == "python" and a.get("complexity") and a["complexity"].get("time_key") is not None:
        c = a["complexity"]
        return jsonify({**base, "reply": f"**Time:** {c['time']}  \n**Space:** {c['space']}  \n_(estimate from code structure)_\n\n{c['explanation']}\n\n{c['space_explanation']}"})
    if it in ("explain_error", "debug_code") and a and not a.get("error") and not a.get("warnings") and not a.get("logic_hints"):
        facts += "\nNo deterministic problem was found; if the output looks wrong the cause is probably logic, so reason carefully and say it is uncertain."
    r = ai.chat(code, history, msg + focus, lang, facts, it)
    if r.get("ai"): return jsonify({**base, "ai": True, "reply": r["reply"]})
    local = _local_explain(a) if it in ("explain_error", "debug_code") else None
    return jsonify({**base, "reply": (local + "\n\n_(AI unavailable, so this is the built-in explanation.)_") if local else None, "error": r.get("error")})

@app.post("/api/upload")
def upload():
    lang = request.form.get("language", "python"); f = request.files.get("file")
    ext = EXT.get(lang, ".py")
    if not f or not f.filename.lower().endswith(ext) and not (lang == "html" and f.filename.lower().endswith(".htm")): raise BadInput(f"Please upload a {ext} file for {lang}.")
    raw = f.read(config.MAX_CODE_BYTES + 1)
    if len(raw) > config.MAX_CODE_BYTES: raise BadInput("File is too large.")
    try: return jsonify(code=raw.decode("utf-8"), filename=f.filename)
    except UnicodeDecodeError: raise BadInput("File must be UTF-8 text.")

@app.post("/api/report")
def make_report():
    d = request.get_json(silent=True); _code(d)
    return send_file(io.BytesIO(report.build_pdf(d)), mimetype="application/pdf", as_attachment=True, download_name="codelens_report.pdf")

@app.get("/api/history")
def history():
    items, ok = db.list_all(); return jsonify(items=items, db_available=ok, message=None if ok else "History is unavailable because MongoDB is not reachable.")
@app.get("/api/history/<i>")
def history_one(i):
    d = db.get(i); return (jsonify(d) if d else (jsonify(error="Not found"), 404))
@app.delete("/api/history/<i>")
def history_del(i): return jsonify(deleted=db.delete(i))

if __name__ == "__main__": app.run(port=5000, debug=False)
