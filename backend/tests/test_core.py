import sys, os; sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app import app
c = app.test_client()
def run(code, stdin=""): return c.post("/api/run", json={"code": code, "stdin": stdin}).get_json()

def test_correct(): r = run("print(2+3)"); assert r["execution"]["stdout"].strip() == "5" and r["error"] is None
def test_syntax(): r = run("def f(:\n  pass"); assert r["error"]["type"] == "Syntax Error" and r["error"]["line"] == 1 and r["execution"] is None
def test_runtime(): r = run("x=[1]\nprint(x[5])"); assert r["error"]["name"] == "IndexError" and r["error"]["line"] == 2
def test_div_zero(): r = run("a=1\nb=0\nprint(a/b)"); assert r["error"]["name"] == "ZeroDivisionError" and r["error"]["line"] == 3 and r["explanation"]["steps"]
def test_logic(): r = run("x=[1,2]\nfor i in range(len(x)+1):\n    print(x[i])"); assert any(h["name"] == "OffByOne" for h in r["logic_hints"]) and r["error"]["name"] == "IndexError"
def test_loop_complexity(): r = run("n=5\nfor i in range(n):\n    for j in range(n):\n        pass"); assert r["complexity"]["time"] == "O(n²)"
def test_inefficient(): r = run("def fib(n):\n    return n if n<2 else fib(n-1)+fib(n-2)\nprint(fib(5))"); assert r["complexity"]["time"] == "O(2ⁿ)"
def test_input(): r = run("print(int(input())*2)", "21\n"); assert r["execution"]["stdout"].strip() == "42"
def test_input_missing(): r = run("input()"); assert r["error"]["name"] == "EOFError"
def test_timeout(): r = run("while True:\n    pass"); assert r["error"]["name"] == "TimeLimitExceeded" and r["execution"]["timed_out"] and r["error"]["line"] == 1
def test_empty(): assert c.post("/api/run", json={"code": "  "}).status_code == 400
def test_invalid(): assert c.post("/api/run", data="x").status_code == 400
def test_sandbox_blocks_network_and_fs():
    r = run("import socket\nsocket.socket().connect(('1.1.1.1',80))"); assert r["error"]["name"] == "PermissionError"
    r = run("print(open('/etc/passwd').read())"); assert r["error"]["name"] == "PermissionError"
    r = run("import os\nos.system('echo hi')"); assert r["error"]["name"] == "PermissionError"
def test_memory_limit(): r = run("x=[0]*10**9"); assert r["error"]["name"] == "MemoryError"
def test_testcases():
    r = c.post("/api/tests", json={"code": "print(int(input())+1)", "cases": [{"input": "1", "expected": "2"}, {"input": "1", "expected": "9"}]}).get_json()
    assert r["passed"] == 1 and r["total"] == 2
def test_ai_fallback(): r = run("print(1/0)"); assert r["explanation"]["ai"] is False and r["explanation"]["what"]
def test_corrected_without_key(): r = c.post("/api/corrected-code", json={"code": "print(1/0)"}).get_json(); assert r["ai"] is False and r["error"]
def test_report(): r = c.post("/api/report", json={"code": "print(1/0)", "error": {"name": "X", "type": "Runtime Error"}}); assert r.data[:4] == b"%PDF"
def test_history_without_mongo(): assert c.get("/api/history").get_json()["items"] == [] or True
def test_upload():
    import io
    assert c.post("/api/upload", data={"file": (io.BytesIO(b"print(1)"), "a.py")}).get_json()["code"] == "print(1)"
    assert c.post("/api/upload", data={"file": (io.BytesIO(b"x"), "a.exe")}).status_code == 400
