"""Static complexity estimation from the AST. Always labelled 'estimated'."""
import ast
EXP = 99
def _mul(a, b): return (a[0] + b[0], a[1] + b[1])
def _fmt(c):
    n, l = c
    if n >= EXP: return "O(2ⁿ)"
    if n == 0 and l == 0: return "O(1)"
    p = []
    if n: p.append({1: "n", 2: "n²", 3: "n³"}.get(n, f"n^{n}"))
    if l: p.append("log n" if l == 1 else f"(log n)^{l}")
    return "O(" + " ".join(p) + ")"
SIMPLE = {"O(1)": "Constant time: work does not grow with input size.",
 "O(log n)": "Logarithmic: the problem shrinks each step, so it grows very slowly.",
 "O(n)": "Linear: work grows in step with the input size.",
 "O(n log n)": "Sorting-like growth, a little more than linear.",
 "O(n²)": "Quadratic: nested loops over the input; doubling the input roughly quadruples the work.",
 "O(n³)": "Cubic: three nested levels; gets slow quickly.", "O(2ⁿ)": "Exponential: work doubles with each extra input item; only usable for tiny inputs."}
LOOPS = (ast.For, ast.AsyncFor, ast.While)

class Analyzer:
    def __init__(self, tree):
        self.tree = tree
        self.funcs = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        self.memo, self.stack, self.notes, self.space = {}, [], [], (0, 0)
    def const_iter(self, it):
        if isinstance(it, ast.Call) and getattr(it.func, "id", "") == "range": return all(isinstance(a, ast.Constant) for a in it.args)
        return isinstance(it, (ast.List, ast.Tuple, ast.Set, ast.Dict, ast.Constant))
    def halving(self, loop):
        for x in ast.walk(loop):
            if isinstance(x, ast.AugAssign) and isinstance(x.op, (ast.FloorDiv, ast.Div, ast.RShift, ast.Mult, ast.LShift)) and isinstance(x.value, ast.Constant) and x.value.value not in (0, 1): return True
            if isinstance(x, ast.Assign) and isinstance(x.value, ast.BinOp) and isinstance(x.value.op, (ast.FloorDiv, ast.Div)) and isinstance(x.value.right, ast.Constant): return True
        return False
    def func_cost(self, name):
        if name in self.memo: return self.memo[name]
        if name in self.stack: return (0, 0)
        f = self.funcs[name]; self.stack.append(name)
        calls = [c for c in ast.walk(f) if isinstance(c, ast.Call) and getattr(c.func, "id", "") == name]
        cached = any("cache" in ast.dump(d).lower() for d in f.decorator_list)
        base = self.block(f.body)
        if calls:
            half = any(isinstance(a, ast.BinOp) and isinstance(a.op, (ast.FloorDiv, ast.Div)) for c in calls for a in c.args)
            if len(calls) >= 2 and not cached:
                base = max(base, (EXP, 0)); self.notes.append(f"`{name}` calls itself {len(calls)} times per call (exponential unless results are cached).")
            elif half:
                base = max(base, (0, 1)); self.notes.append(f"`{name}` recurses on a halved input (logarithmic).")
            else:
                base = max(base, (1, 0)); self.notes.append(f"`{name}` is recursive (about n calls).")
            self.space = max(self.space, (0, 1) if half and len(calls) < 2 else (1, 0))
        self.stack.pop(); self.memo[name] = base; return base
    def expr(self, node):
        best = (0, 0)
        for x in ast.walk(node):
            if isinstance(x, ast.Call):
                fn = getattr(x.func, "id", getattr(x.func, "attr", ""))
                if fn in ("sorted", "sort"): best = max(best, (1, 1)); self.notes.append("Sorting adds O(n log n).")
                elif fn in ("sum", "min", "max", "list", "set", "tuple", "any", "all", "join", "reversed") and x.args or fn in ("count", "index"): best = max(best, (1, 0))
                elif fn in self.funcs: best = max(best, self.func_cost(fn))
            if isinstance(x, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                c = (0, 0)
                for g in x.generators:
                    if not self.const_iter(g.iter): c = _mul(c, (1, 0))
                best = max(best, c)
                if not isinstance(x, ast.GeneratorExp): self.space = max(self.space, (c[0], 0))
        return best
    def stmt(self, s):
        if isinstance(s, (ast.FunctionDef, ast.ClassDef)): return (0, 0)
        if isinstance(s, LOOPS):
            if isinstance(s, ast.While): f, head = ((0, 1) if self.halving(s) else (1, 0)), self.expr(s.test)
            else: f, head = ((0, 0) if self.const_iter(s.iter) else (1, 0)), self.expr(s.iter)
            return max(head, _mul(f, self.block(s.body + s.orelse)))
        cost = (0, 0)
        for fld in ("body", "orelse", "finalbody"):
            if hasattr(s, fld): cost = max(cost, self.block(getattr(s, fld)))
        for h in getattr(s, "handlers", []): cost = max(cost, self.block(h.body))
        if hasattr(s, "test"): cost = max(cost, self.expr(s.test))
        if not hasattr(s, "body"): cost = max(cost, self.expr(s))
        return cost
    def block(self, stmts): return max([self.stmt(s) for s in stmts] or [(0, 0)])
    def loop_space(self):
        def walk(n, depth):
            best = (0, 0)
            for c in ast.iter_child_nodes(n):
                d = depth + (1 if isinstance(c, LOOPS) and not (isinstance(c, ast.For) and self.const_iter(c.iter)) else 0)
                if depth and isinstance(c, ast.Call) and getattr(c.func, "attr", "") in ("append", "add", "extend", "insert"): best = max(best, (depth, 0))
                if depth and isinstance(c, ast.Assign) and any(isinstance(t, ast.Subscript) for t in c.targets): best = max(best, (depth, 0))
                best = max(best, walk(c, d))
            return best
        return walk(self.tree, 0)

def analyze(code):
    tree = ast.parse(code); a = Analyzer(tree)
    t = a.block(tree.body)
    for n in a.funcs: t = max(t, a.func_cost(n))
    sp = max(a.space, a.loop_space())
    ts, ss = _fmt(t), _fmt(sp)
    return {"time": ts, "space": ss, "time_key": list(t), "space_key": list(sp), "confidence": "estimated",
            "explanation": (SIMPLE.get(ts, "") + " " + " ".join(dict.fromkeys(a.notes))).strip(),
            "space_explanation": "Extra memory does not grow with input." if ss == "O(1)" else f"Extra memory grows as {ss} (lists/dicts built in loops, or recursion depth).",
            "limitations": ["Estimated from code structure only; n is assumed to be the size of the main input.",
                            "Library calls and data-dependent loop counts are approximated.", "Not a formal proof."]}

def better(a, b):
    """True if complexity key a is strictly better than b."""
    return tuple(a) < tuple(b)
