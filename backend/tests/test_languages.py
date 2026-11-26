import sys, os, shutil, pytest; sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app import app
c = app.test_client()
def run(lang, code, stdin=""): return c.post("/api/run", json={"code": code, "language": lang, "stdin": stdin}).get_json()

def test_languages_endpoint():
    ids = {l["id"]: l for l in c.get("/api/languages").get_json()["languages"]}
    assert set(ids) == {"python", "c", "cpp", "java", "javascript", "html", "css", "sql"}
    assert ids["java"]["available"] == bool(shutil.which("javac") and shutil.which("java"))
@pytest.mark.skipif(shutil.which("javac"), reason="javac present")
def test_missing_runtime_reported_not_faked():
    r = c.post("/api/run", json={"code": "class A{}", "language": "java"}); assert r.status_code == 400 and "not installed" in r.get_json()["error"]
def test_unsupported_language(): assert c.post("/api/run", json={"code": "x", "language": "cobol"}).status_code == 400

# --- Python deterministic examples from the brief
def test_py_mul_assign_eq():
    r = run("python", "a = 10\nb = 5\nprint(a *== b)"); e = r["error"]
    assert e["type"] == "Syntax Error" and e["line"] == 3 and any("*=" in s for s in e["suggestions"]) and r["execution"] is None
def test_py_assign_in_if():
    e = run("python", 'a = 10\nif a = 10:\n    print("Equal")')["error"]; assert e["line"] == 2 and any("==" in s for s in e["suggestions"])
def test_py_nameerror(): e = run("python", "print(total)")["error"]; assert e["name"] == "NameError" and e["line"] == 1 and "total" in e["message"]

# --- C / C++ / JS / HTML / CSS / SQL: valid, syntax error, execution/validation
def test_c():
    assert run("c", '#include <stdio.h>\nint main(){printf("hi\\n");return 0;}')["execution"]["stdout"].strip() == "hi"
    e = run("c", "#include <stdio.h>\nint main(){\n int a = 5\n printf(\"%d\", a);\n return 0;\n}")["error"]; assert e["type"] == "Syntax Error" and e["line"] in (3, 4)
def test_cpp():
    assert run("cpp", '#include <iostream>\nint main(){int n; std::cin>>n; std::cout<<n*2;}', "4")["execution"]["stdout"] == "8"
    e = run("cpp", "#include <iostream>\nint main(){\n std::cout << y;\n}")["error"]; assert e["line"] == 3 and "not declared" in e["message"]
def test_c_timeout(): assert run("c", "int main(){while(1){} }")["error"]["name"] == "TimeLimitExceeded"
def test_js():
    assert run("javascript", "console.log(2+3)")["execution"]["stdout"].strip() == "5"
    e = run("javascript", "let a = ;\nconsole.log(a)")["error"]; assert e["name"] == "SyntaxError" and e["line"] == 1
    e = run("javascript", "const o = null;\nconsole.log(o.x);")["error"]; assert e["name"] == "TypeError" and e["line"] == 2
@pytest.mark.skipif(not shutil.which("javac"), reason="no JDK in this environment")
def test_java():
    assert run("java", 'public class Main{public static void main(String[] a){System.out.println("hi");}}')["execution"]["stdout"].strip() == "hi"
    assert run("java", 'public class Main{public static void main(String[] a){int x = ;}}')["error"]["type"] == "Syntax Error"
def test_html():
    ok = run("html", '<!DOCTYPE html><html lang="en"><head><title>t</title></head><body><main><p>hi</p></main></body></html>')
    assert ok["error"] is None and ok["warnings"] == []
    r = run("html", '<div>\n<p>text\n</div>\n<img src="a.png">'); assert r["error"]["name"] == "UnclosedTag" and r["error"]["line"] == 2
    assert any(w["code"] == "MissingAlt" for w in r["warnings"])
def test_css():
    assert run("css", "body {\n color: red;\n margin: 0;\n}")["error"] is None
    r = run("css", "p {\n color: red\n colour: blue;\n}"); assert r["error"]["name"] == "MissingSemicolon" and r["error"]["line"] == 2
    assert any(w["code"] == "UnknownProperty" for w in r["warnings"])
    assert run("css", "p { color: red;")["error"]["name"] == "UnclosedBrace"
def test_sql():
    r = run("sql", "CREATE TABLE t(a INT);\nINSERT INTO t VALUES (1),(2);\nSELECT a FROM t WHERE a>1;"); assert r["error"] is None and "2" in r["execution"]["stdout"]
    assert run("sql", "SELECT FROM t WHERE;")["error"]["name"] == "SQLSyntaxError"
    e = run("sql", "SELECT * FROM nothere;")["error"]; assert e["name"] == "SQLRuntimeError" and "no such table" in e["message"]
    assert any(w["code"] == "MissingWhere" for w in run("sql", "CREATE TABLE t(a);\nDELETE FROM t;")["warnings"])
def test_sql_blocks_attach(): assert run("sql", "ATTACH DATABASE '/tmp/x.db' AS x;")["error"] is not None
def test_complexity_not_forced():
    for l, code in (("html", "<p>x</p>"), ("css", "p{color:red;}"), ("sql", "SELECT 1;")): assert run(l, code)["complexity"]["time"] == "N/A"
