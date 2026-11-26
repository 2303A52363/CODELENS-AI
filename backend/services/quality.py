"""Code quality score with an explained breakdown."""
import ast
def score(code, issues):
    tree = ast.parse(code); lines = [l for l in code.splitlines() if l.strip()]
    funcs = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    comments = sum(1 for l in lines if l.strip().startswith("#"))
    documented = sum(1 for f in funcs if ast.get_docstring(f))
    long_lines = sum(1 for l in lines if len(l) > 100)
    bad_names = sum(1 for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store) and len(n.id) == 1 and n.id not in "ijkxyn_")
    read = 100 - 15 * long_lines - 10 * bad_names
    read = min(100, read + (10 if comments else 0) + (10 if funcs and documented == len(funcs) else 0))
    avg_len = (sum((f.end_lineno - f.lineno + 1) for f in funcs) / len(funcs)) if funcs else 0
    def depth(n, d=0):
        return max([depth(c, d + isinstance(c, (ast.If, ast.For, ast.While, ast.Try))) for c in ast.iter_child_nodes(n)] or [d])
    nest = depth(tree)
    struct = 100 - max(0, avg_len - 25) * 2 - max(0, nest - 3) * 15 - (10 if len(lines) > 25 and not funcs else 0)
    mi = None
    try:
        from radon.metrics import mi_visit; from radon.complexity import cc_visit
        mi = mi_visit(code, True); cc = cc_visit(code); avg_cc = sum(b.complexity for b in cc) / len(cc) if cc else 1
        maint = 0.6 * mi + 0.4 * max(0, 100 - (avg_cc - 5) * 8) if avg_cc > 5 else 0.6 * mi + 40
    except Exception:
        maint = 70
    issue = 100 - 12 * len(issues)
    parts = {"readability": read, "structure": struct, "maintainability": maint, "issues": issue}
    parts = {k: round(max(0, min(100, v))) for k, v in parts.items()}
    total = round(sum(parts.values()) / 4)
    return {"score": total, "breakdown": parts, "explanation": [
        "Score = average of four parts (0-100 each).",
        f"Readability: long lines ({long_lines}), single-letter names ({bad_names}), comments/docstrings add points.",
        f"Structure: average function length {avg_len:.0f} lines, max nesting {nest} (deeper than 3 loses points).",
        "Maintainability: Radon maintainability index and cyclomatic complexity" + (f" (MI={mi:.0f})." if mi is not None else " (Radon unavailable; default used)."),
        f"Issues: {len(issues)} Ruff/rule warning(s), 12 points each."]}
