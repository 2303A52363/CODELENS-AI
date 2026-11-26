import sys, os, json; sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app import app
from services import ai
from nlp import intent
c = app.test_client()
def chat(msg, code="print(1/0)", lang="python", hist=None): return c.post("/api/chat", json={"message": msg, "code": code, "language": lang, "history": hist or []}).get_json()

def test_metrics_are_real_and_heldout():
    m = json.load(open(os.path.join(os.path.dirname(intent.__file__), "metrics.json")))
    assert m["test"] >= 40 and m["train"] > m["test"] and 0.5 < m["accuracy"] <= 1.0 and set(m["labels"]) == {"correct_code", "debug_code", "explain_code", "explain_complexity", "explain_error", "generate_tests", "optimize_code", "general_question"}
def test_unseen_sentences():
    cases = {"What is the big o of my function?": "explain_complexity", "Make my program run faster": "optimize_code", "Write some tests for this": "generate_tests",
             "Why did this crash with an exception?": "explain_error", "Explain line 4": "explain_code", "Fix the mistakes and give me the final code": "correct_code"}
    got = {t: intent.classify(t)["intent"] for t in cases}
    assert sum(got[t] == i for t, i in cases.items()) >= 5, got
def test_unknown_is_low_confidence():
    r = intent.classify("purple elephants dancing on mars"); assert r["low_confidence"] and r["intent"] == "general_question"
def test_line_extraction(): assert intent.classify("explain the fifth line")["line"] == 5 and intent.classify("what does line 12 do")["line"] == 12
def test_classify_endpoint(): assert c.post("/api/nlp/classify", json={"text": "optimize my code"}).get_json()["intent"] == "optimize_code"

def test_chat_validation():
    assert c.post("/api/chat", json={"message": "  ", "code": "x"}).status_code == 400
    assert "no code" in chat("explain this code", code="")["reply"].lower()
def test_chat_explain_error_works_without_gemini(monkeypatch):
    monkeypatch.setattr(ai, "_call", lambda *a, **k: (None, "Gemini API key is not configured"))
    r = chat("Why am I getting this error?", "a = 1\nb = 0\nprint(a/b)"); assert r["intent"]["intent"] == "explain_error" and "ZeroDivisionError" in r["reply"] and "line 3" in r["reply"] and r["ai"] is False
def test_chat_complexity_is_deterministic():
    r = chat("what is the time complexity?", "n=5\nfor i in range(n):\n    for j in range(n):\n        pass"); assert "O(n²)" in r["reply"]
def test_chat_gemini_failure_is_reported_not_faked(monkeypatch):
    monkeypatch.setattr(ai, "_call", lambda *a, **k: (None, "Gemini quota or rate limit reached."))
    r = chat("what is recursion?", "x=1"); assert r["reply"] is None and "quota" in r["error"]
def test_chat_uses_context_and_history(monkeypatch):
    seen = {}
    def fake(prompt, system, as_json=True): seen["p"] = prompt; return "ok", None
    monkeypatch.setattr(ai, "_call", fake)
    chat("explain the second line", "x = 1\ny = x + 1", hist=[{"role": "student", "text": "earlier question"}])
    p = seen["p"]; assert "y = x + 1" in p and "earlier question" in p and "explain_code" in p and "Language: python" in p

# --- Correction verification gate (Gemini mocked: tests OUR validation pipeline, not Gemini itself)
def _mock(code):
    return lambda prompt, system, as_json=True: ({"corrected_code": code, "changes": ["changed"]}, None)
def test_good_correction_verified(monkeypatch):
    monkeypatch.setattr(ai, "_call", _mock("a = 1\nb = 1\nprint(a/b)"))
    r = c.post("/api/corrected-code", json={"code": "a=1\nb=0\nprint(a/b)", "language": "python"}).get_json()
    assert r["validation"]["verified"] is True and "Verified" in r["disclaimer"]
def test_bad_correction_not_verified(monkeypatch):
    monkeypatch.setattr(ai, "_call", _mock("print(1 +"))
    r = c.post("/api/corrected-code", json={"code": "print(1/0)", "language": "python"}).get_json()
    assert r["validation"]["verified"] is False and "NOT VERIFIED" in r["disclaimer"]
def test_correction_that_still_crashes_not_verified(monkeypatch):
    monkeypatch.setattr(ai, "_call", _mock("print(1/0)"))
    assert c.post("/api/corrected-code", json={"code": "print(1/0)", "language": "python"}).get_json()["validation"]["verified"] is False
def test_chat_correct_action_flags_unverified(monkeypatch):
    monkeypatch.setattr(ai, "_call", _mock("print(1/0)"))
    r = chat("fix the error in my code"); assert r["action"]["type"] == "corrected_code" and r["action"]["verified"] is False and "Not verified" in r["reply"]
def test_optimize_flow_with_mock(monkeypatch):
    slow = "t = 0\nfor i in range(2000):\n    for j in range(200):\n        t += 1\nprint(t)"
    monkeypatch.setattr(ai, "_call", lambda *a, **k: ({"issues": [], "optimized_code": "print(400000)", "summary": "closed form"}, None))
    r = c.post("/api/optimize", json={"code": slow, "language": "python"}).get_json()
    assert r["measured"]["same_output"] is True and "improved" in r["verdict"] or "faster" in r["verdict"]
    monkeypatch.setattr(ai, "_call", lambda *a, **k: ({"issues": [], "optimized_code": "print(1)", "summary": "x"}, None))
    assert "Could not verify" in c.post("/api/optimize", json={"code": slow, "language": "python"}).get_json()["verdict"]
def test_gemini_http_errors_mapped(monkeypatch):
    import requests, config
    monkeypatch.setattr(config, "GEMINI_API_KEY", "x")
    class R: 
        def __init__(s, code): s.status_code = code
    for code, word in ((401, "Invalid"), (429, "quota"), (500, "error")):
        monkeypatch.setattr(requests, "post", lambda *a, code=code, **k: R(code)); d, e = ai._call("p", "s"); assert d is None and word.lower() in e.lower()
    def to(*a, **k): raise requests.Timeout()
    monkeypatch.setattr(requests, "post", to); assert "timed out" in ai._call("p", "s")[1]
    monkeypatch.setattr(requests, "post", lambda *a, **k: R(404)); assert "not found" in ai._call("p", "s")[1].lower()
def test_generate_tests_records_actual_output(monkeypatch):
    monkeypatch.setattr(ai, "_call", lambda *a, **k: ({"cases": [{"category": "normal", "input": "3", "description": "d"}]}, None))
    r = c.post("/api/generate-tests", json={"code": "print(int(input())*2)", "language": "python"}).get_json(); assert r["cases"][0]["actual_output"] == "6"
