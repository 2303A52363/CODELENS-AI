import io
from xml.sax.saxutils import escape
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Preformatted, Spacer
def build_pdf(data):
    buf = io.BytesIO(); s = getSampleStyleSheet(); doc = SimpleDocTemplate(buf, pagesize=A4, title="Code Review Report")
    P = lambda t, st="BodyText": Paragraph(escape(str(t)), s[st])
    el = [P("CodeLens AI - Review Report", "Title"), P(f"Language: {data.get('language', 'python')}"), P("Code", "Heading2"),
          Preformatted(data.get("code", "")[:6000], s["Code"])]
    e = data.get("error")
    el += [P("Error Analysis", "Heading2")]
    if e:
        el += [P(f"{e['name']} ({e['type']}) at line {e.get('line') or 'unknown'}: {e.get('message', '')}"), P(f"Line: {e.get('code_line', '')}")]
        x = data.get("explanation") or {}
        for k in ("what", "why", "fix", "learn"): 
            if x.get(k): el.append(P(f"{k.title()}: {x[k]}"))
        el += [P(f"{i + 1}. {t}") for i, t in enumerate(x.get("steps", []))]
    else: el.append(P("No errors detected."))
    c = data.get("complexity")
    if c: el += [P("Complexity (estimated)", "Heading2"), P(f"Time {c['time']}, Space {c['space']}. {c.get('explanation', '')}")]
    q = data.get("quality")
    if q: el += [P("Quality Score", "Heading2"), P(f"{q['score']}/100 - {q['breakdown']}")] + [P(t) for t in q["explanation"]]
    o = data.get("optimization")
    if o: el += [P("Optimization", "Heading2"), P(o.get("summary", "")), P(o.get("verdict", ""))]
    el += [Spacer(1, 12), P("AI suggestions should be tested before use.")]
    doc.build(el); return buf.getvalue()
