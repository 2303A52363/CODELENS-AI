"""Deterministic error detection: AST syntax check, traceback parsing, Ruff, rule-based logic hints."""
import ast, re, json, subprocess, shutil, sys

KB = {
 "SyntaxError": ("Python could not understand the structure of your code, so it never ran.",
   "Something is missing or misplaced: a colon, bracket, quote, or keyword.",
   ["Go to the highlighted line (also check the line just above it).", "Look for an unclosed ( [ { or quote.", "Check that if/for/while/def lines end with a colon.", "Run again."],
   "Python needs exact punctuation; the reported line is where it noticed the problem, not always where you made it."),
 "IndentationError": ("The spaces at the start of a line don't match the block structure.",
   "Python uses indentation to group code, and this line is indented inconsistently.",
   ["Look at the highlighted line and the lines around it.", "Use 4 spaces per level; never mix tabs and spaces.", "Make sure code after a ':' is indented.", "Run again."],
   "Indentation is syntax in Python, not just style."),
 "NameError": ("You used a name that Python doesn't know.", "The variable/function was never defined, is misspelled, or is defined later or in another scope.",
   ["Find the name on the highlighted line.", "Check the spelling (case matters).", "Make sure it is assigned/defined before this line.", "Run again."],
   "Names must exist before they are used."),
 "TypeError": ("An operation was used on a value of the wrong type.", "e.g. adding a string to a number, or calling something that isn't a function.",
   ["Read the error message to see which two types clashed.", "Print the types with type(x) on the highlighted line.", "Convert with int(), str() or float() where needed.", "Run again."],
   "Check the types of values when an operation fails."),
 "ZeroDivisionError": ("The program tried to divide by zero.", "The divisor was 0 when the division ran.",
   ["Find the / // or % on the highlighted line.", "Print the divisor just before it to see its value.", "Add a check: if divisor != 0 (or handle it with try/except).", "Run again."],
   "Validate a divisor before dividing."),
 "IndexError": ("You asked for a list position that does not exist.", "The index was >= the list length (or too negative); often an off-by-one in a loop.",
   ["Print len(list) and the index you use.", "Remember valid indexes are 0 to len-1.", "Fix the loop range or add a bounds check.", "Run again."],
   "Lists start at 0, so the last index is len-1."),
 "KeyError": ("A dictionary key was looked up but is not in the dictionary.", "The key is missing or spelled differently.",
   ["Print the dictionary keys.", "Check spelling/type of the key.", "Use dict.get(key, default) or check 'key in dict' first.", "Run again."],
   "Use .get() when a key may be missing."),
 "ValueError": ("A function got the right type but an unacceptable value.", "For example int('abc') cannot be converted.",
   ["Look at the value passed on the highlighted line.", "Validate the input before converting.", "Wrap conversion in try/except ValueError if input is user-typed.", "Run again."],
   "Validate user input before using it."),
 "AttributeError": ("You used an attribute/method that the object doesn't have.", "The object is a different type than expected (often None) or the name is misspelled.",
   ["Identify the object before the dot.", "Print type(obj) and obj.", "Check the method name with dir(obj) or the docs.", "Run again."],
   "Know what type an object is before calling methods on it."),
 "ModuleNotFoundError": ("Python could not find the module you imported.", "It is misspelled, not installed, or not available in the sandbox.",
   ["Check the import spelling.", "Third-party packages are not installed in the sandbox; use the standard library.", "Run again."], "Imports must be available in the environment."),
 "RecursionError": ("A function called itself too many times.", "There is no base case, or it is never reached.",
   ["Find the recursive function.", "Add a base case that returns without recursing.", "Ensure each call moves closer to the base case.", "Run again."], "Every recursion needs a reachable base case."),
 "EOFError": ("The program asked for input but none was provided.", "input() was called and the Input box was empty or had too few lines.",
   ["Count the input() calls in your code.", "Type one value per line in the Input box.", "Run again."], "Programs reading input need input supplied beforehand here."),
 "TimeLimitExceeded": ("The program ran longer than the allowed time and was stopped.", "Likely an infinite loop or a very slow algorithm.",
   ["Look at your while loops: does the loop variable change?", "Check the loop condition can become False.", "Add a print inside the loop to see progress.", "Run again."], "Loops need a condition that eventually ends."),
 "MemoryError": ("The program used more memory than allowed.", "It built a huge list/string, or recursed without end.",
   ["Look for loops that keep appending.", "Process data in smaller chunks.", "Run again."], "Memory is limited; avoid unbounded growth."),
}
DEFAULT_KB = ("The program raised an error while running.", "See the error message for the exact reason.",
   ["Read the last line of the error message.", "Go to the highlighted line.", "Print the values used on that line.", "Run again."], "Error messages tell you what and where.")

def kb_explanation(name):
    w, y, steps, learn = KB.get(name, DEFAULT_KB)
    return {"what": w, "why": y, "fix": steps[2] if len(steps) > 2 else steps[-1], "steps": steps, "learn": learn}

def _line(code, n):
    ls = code.splitlines()
    return ls[n - 1] if n and 1 <= n <= len(ls) else ""

def detect_syntax(code):
    try:
        ast.parse(code); return None
    except SyntaxError as e:
        return {"name": type(e).__name__, "type": "Syntax Error", "line": e.lineno, "code_line": _line(code, e.lineno),
                "message": e.msg, "source": "python-ast", "line_reliable": True}

def parse_traceback(stderr, code):
    lines = stderr.strip().splitlines()
    if not lines: return None
    m = re.match(r"^([A-Za-z_][\w.]*)(?::\s*(.*))?$", lines[-1])
    if not m: return {"name": "RuntimeError", "type": "Runtime Error", "line": None, "code_line": "", "message": lines[-1], "source": "traceback", "line_reliable": False}
    frames = re.findall(r'File "<student>", line (\d+)', stderr)
    ln = int(frames[-1]) if frames else None
    name = m.group(1).split(".")[-1]
    return {"name": name, "type": "Runtime Error", "line": ln, "code_line": _line(code, ln), "message": m.group(2) or "",
            "source": "python-traceback", "line_reliable": ln is not None, "traceback": stderr.strip()[-1500:]}

def timeout_error(code):
    cand = None
    for n in ast.walk(ast.parse(code)):
        if isinstance(n, ast.While) and not any(isinstance(x, (ast.Break, ast.Return)) for x in ast.walk(n)):
            cand = n; break
    ln = cand.lineno if cand else None
    return {"name": "TimeLimitExceeded", "type": "Execution Error", "line": ln, "code_line": _line(code, ln),
            "message": "Execution exceeded the time limit.", "source": "sandbox-timeout", "line_reliable": False,
            "note": "Line is a likely suspect (a while loop with no break), not a certainty." if ln else "No obvious loop found."}

def run_ruff(code):
    exe = shutil.which("ruff")
    cmd = [exe] if exe else [sys.executable, "-m", "ruff"]
    try:
        p = subprocess.run(cmd + ["check", "--select", "E,F,B", "--ignore", "E501", "--output-format", "json", "--stdin-filename", "main.py", "-"],
                           input=code, capture_output=True, text=True, timeout=10)
        return [{"line": i["location"]["row"], "code": i["code"], "message": i["message"]} for i in json.loads(p.stdout or "[]")]
    except Exception:
        return []

def logic_hints(code):
    try: tree = ast.parse(code)
    except SyntaxError: return []
    out = []
    def add(n, name, msg): out.append({"line": n.lineno, "name": name, "message": msg})
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for d in n.args.defaults:
                if isinstance(d, (ast.List, ast.Dict, ast.Set)): add(d, "MutableDefault", "Mutable default argument is shared between calls.")
        if isinstance(n, ast.Compare):
            for op, c in zip(n.ops, n.comparators):
                if isinstance(op, (ast.Eq, ast.NotEq)) and isinstance(c, ast.Constant) and c.value is None:
                    add(n, "NoneComparison", "Use 'is None' instead of '== None'.")
                if isinstance(op, (ast.Is, ast.IsNot)) and isinstance(c, ast.Constant) and not isinstance(c.value, (type(None), bool)):
                    add(n, "IsWithLiteral", "'is' compares identity; use '==' to compare values.")
        if isinstance(n, ast.While) and isinstance(n.test, ast.Constant) and n.test.value and not any(isinstance(x, (ast.Break, ast.Return)) for x in ast.walk(n)):
            add(n, "InfiniteLoop", "'while True' with no break/return will never stop.")
        if isinstance(n, ast.BinOp) and isinstance(n.op, (ast.Div, ast.FloorDiv, ast.Mod)) and isinstance(n.right, ast.Constant) and n.right.value == 0:
            add(n, "DivisionByZero", "Dividing by the constant 0.")
        if isinstance(n, ast.For) and isinstance(n.iter, ast.Call) and getattr(n.iter.func, "id", "") == "range" and n.iter.args:
            a = n.iter.args[0] if len(n.iter.args) == 1 else n.iter.args[1]
            if isinstance(a, ast.BinOp) and isinstance(a.op, ast.Add) and isinstance(a.left, ast.Call) and getattr(a.left.func, "id", "") == "len":
                add(n, "OffByOne", "range(len(x) + k) goes past the last index; x[i] may raise IndexError.")
    return out

def syntax_hint(code, err):
    """Deterministic, intent-aware advice for common Python syntax slips. Never assumes a single 'right' fix."""
    line = err.get("code_line", "") or ""; sug = []
    m = re.search(r"(\*|\+|-|/)==", line)
    if m:
        o = m.group(1)
        sug = [f"`{o}==` is not a Python operator. Pick the one you meant:",
               f"  • `{o}=` — compound assignment (e.g. `a {o}= b` updates a in place; it is a statement, so it cannot be used inside print(...)).",
               f"  • `{o}` — plain arithmetic (e.g. `print(a {o} b)` shows the result without changing a).",
               "  • `==` — comparison that gives True/False (e.g. `a == b`)."]
    elif re.match(r"\s*(if|elif|while)\b[^=<>!]*[^=<>!:]=[^=]", line):
        sug = ["`=` assigns a value; a condition needs a comparison.", "Replace `=` with `==` to test equality (for example `if a == 10:`)."]
    elif err.get("name") == "SyntaxError" and re.match(r"\s*(if|elif|else|for|while|def|class)\b.*[^:]\s*$", line) and "expected ':'" in err.get("message", ""):
        sug = ["Block statements (if/for/while/def/class) must end with a colon `:`."]
    return sug
