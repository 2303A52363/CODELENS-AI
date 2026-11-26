import { useState, useEffect } from "react";
import Editor from "./Editor.jsx";
import Diff from "./Diff.jsx";
import { api } from "../api.js";
const copy = (t) => navigator.clipboard?.writeText(t);

export function Output({ r }) {
  if (!r) return <p className="muted">Click “Run &amp; Analyze” to see the program output.</p>;
  const ex = r.execution;
  if (!ex) return <p className="muted">The program was not run because of a syntax error. See the Errors tab.</p>;
  return <div><pre className="out">{ex.stdout || <span className="muted">(no output)</span>}</pre>
    {ex.stderr && <pre className="out err">{ex.stderr}</pre>}
    <p className="muted">Exit code {ex.exit_code} · {ex.duration_ms} ms{ex.timed_out ? " · stopped: time limit" : ""}{ex.truncated ? " · output truncated" : ""}</p></div>;
}

export function Errors({ r, code, language, stdin, onLoad, onRun }) {
  const [fix, setFix] = useState(null); const [busy, setBusy] = useState(false);
  if (!r) return <p className="muted">No analysis yet.</p>;
  const e = r.error, x = r.explanation;
  const show = async () => { setBusy(true); try { setFix(await api.corrected(code, e, language, stdin)); } catch (err) { setFix({ error: err.message }); } setBusy(false); };
  const v = fix?.validation;
  return <div>
    {!e && <p className="ok">✔ No errors detected.</p>}
    {e && <div className="card bad">
      <h3>{e.name} <span className="tag">{e.type}</span></h3>
      <p><b>Line:</b> {e.line ?? "unknown"}{!e.line_reliable && e.line ? " (likely, not certain)" : ""}</p>
      {e.code_line && <pre className="out">{e.code_line}</pre>}
      <p className="muted">{e.message}</p>{e.note && <p className="muted">{e.note}</p>}
      {e.suggestions?.length > 0 && <div className="card"><b>Suggested correction</b>{e.suggestions.map((t, i) => <div key={i} style={{ whiteSpace: "pre-wrap" }}>{t}</div>)}</div>}
      <p className="muted">Detected by: {e.source}</p></div>}
    {x && <div className="card">
      <p><b>What happened?</b> {x.what}</p><p><b>Why?</b> {x.why}</p><p><b>How to fix:</b> {x.fix}</p>
      <b>Steps</b><ol>{x.steps.map((s, i) => <li key={i}>{s}</li>)}</ol><p><b>Learn:</b> {x.learn}</p>
      {!x.ai && <p className="muted">Built-in explanation shown. {x.ai_note}</p>}</div>}
    {(r.warnings.length > 0 || r.logic_hints.length > 0) && <div className="card"><b>Warnings</b><ul>
      {r.warnings.map((w, i) => <li key={"w" + i}>Line {w.line ?? "–"} <code>{w.code}</code>: {w.message}</li>)}
      {r.logic_hints.map((h, i) => <li key={"h" + i}>Line {h.line}: {h.message}</li>)}</ul></div>}
    {e && <><button onClick={show} disabled={busy}>{busy ? "Asking AI + validating…" : fix?.corrected_code ? "Try another correction" : "Show Complete Corrected Code"}</button>
      {fix?.error && <p className="warn">{fix.error}</p>}
      {fix?.corrected_code && <div className="card">
        <p className={v?.verified ? "ok" : "warn"}><b>{v?.verified ? "✔ Verified" : "✖ Not verified"}</b> — {v?.message} <span className="muted">({v?.method})</span></p>
        <p className="muted">{fix.disclaimer}</p>
        <Diff original={code} changed={fix.corrected_code} labels={["Your code", "Suggested"]} />
        <ul>{(fix.changes || []).map((c, i) => <li key={i}>{c}</li>)}</ul>
        <button onClick={() => copy(fix.corrected_code)}>Copy code</button>
        <button onClick={() => onLoad(fix.corrected_code)}>Replace editor contents</button>
        <button onClick={() => { onLoad(fix.corrected_code); onRun(fix.corrected_code); }}>Replace &amp; run</button></div>}</>}
  </div>;
}

export function Complexity({ r }) {
  const c = r?.complexity;
  if (!c) return <p className="muted">Complexity appears after a successful analysis.</p>;
  return <div className="card"><div className="stats"><div><small>Time</small><h2>{c.time}</h2></div><div><small>Space</small><h2>{c.space}</h2></div></div>
    <span className="tag">{c.confidence}</span><p>{c.explanation}</p><p>{c.space_explanation}</p>
    <b>Limitations</b><ul>{c.limitations.map((l, i) => <li key={i}>{l}</li>)}</ul></div>;
}

export function Quality({ r }) {
  const q = r?.quality; if (!q) return <p className="muted">Quality score appears after a successful analysis.</p>;
  return <div className="card"><h2>{q.score}/100</h2>
    {Object.entries(q.breakdown).map(([k, v]) => <div key={k} className="bar"><span>{k}</span><i style={{ width: v + "%" }} /><em>{v}</em></div>)}
    <b>How it is calculated</b><ul>{q.explanation.map((t, i) => <li key={i}>{t}</li>)}</ul></div>;
}

export function Tests({ code, language, stdin, loaded }) {
  const [cases, setCases] = useState([{ input: "", expected: "" }]); const [res, setRes] = useState(null); const [err, setErr] = useState(""); const [note, setNote] = useState(""); const [busy, setBusy] = useState(false);
  useEffect(() => { if (loaded?.length) { setCases(loaded.map((c) => ({ input: c.input ?? "", expected: "", hint: `${c.category}: ${c.description}`, actual: c.actual_output }))); setRes(null); } }, [loaded]);
  const set = (i, k, v) => setCases(cases.map((c, j) => (j === i ? { ...c, [k]: v } : c)));
  const run = async () => { setErr(""); try { setRes(await api.tests(code, cases, language)); } catch (e) { setErr(e.message); } };
  const gen = async () => { setBusy(true); setErr(""); try { const d = await api.genTests(code, language); if (!d.cases.length) setErr(d.error || "No test cases returned."); else { setCases(d.cases.map((c) => ({ input: c.input, expected: "", hint: `${c.category}: ${c.description}`, actual: c.actual_output }))); setNote(d.note); setRes(null); } } catch (e) { setErr(e.message); } setBusy(false); };
  return <div><button onClick={gen} disabled={busy}>{busy ? "Generating…" : "Generate test cases (AI)"}</button>{note && <p className="muted">{note}</p>}
    {cases.map((c, i) => <div className="case" key={i}>{c.hint && <small className="muted" style={{ width: "100%" }}>{c.hint}{c.actual !== undefined ? ` · program printed: ${c.actual}` : ""}</small>}
    <textarea placeholder="Input (one value per line)" value={c.input} onChange={(e) => set(i, "input", e.target.value)} />
    <textarea placeholder="Expected output (you decide)" value={c.expected} onChange={(e) => set(i, "expected", e.target.value)} />
    {res?.results[i] && <b className={res.results[i].passed ? "ok" : "warn"}>{res.results[i].passed ? "PASS" : "FAIL: got " + JSON.stringify(res.results[i].actual)}</b>}</div>)}
    <button onClick={() => setCases([...cases, { input: "", expected: "" }])}>+ Add case</button><button onClick={run}>Run test cases</button>
    {err && <p className="warn">{err}</p>}{res && <p>{res.passed}/{res.total} passed</p>}</div>;
}

export function Optimize({ data, busy, code, language, onLoad }) {
  if (busy) return <p className="muted">Analyzing…</p>;
  if (!data) return <p className="muted">Click “Optimize Code”. Works even when your program has no errors.</p>;
  if (data.error && !data.optimized_code) return <div>
    <p className="warn">{data.error}</p>
    {data.static_findings?.length > 0 && <div className="card"><b>Static findings (no AI)</b><ul>{data.static_findings.map((f, i) => <li key={i}>{f.line ? `Line ${f.line}: ` : ""}{f.problem}</li>)}</ul></div>}</div>;
  const v = data.validation;
  return <div>
    <div className="card"><p>{data.summary}</p>
      <ul>{(data.issues || []).map((s, i) => <li key={i}>Line {s.line}: {s.problem} <i className="muted">— {s.why_it_matters}</i></li>)}</ul>
      {v && <p className={v.verified ? "ok" : "warn"}><b>{v.verified ? "✔ Validated" : "✖ Failed validation"}</b> — {v.message}</p>}
      <p><b>Verdict:</b> {data.verdict}</p>
      {data.measured && <p className="muted">Measured (median of 3): original {data.measured.original_ms}ms · optimized {data.measured.optimized_ms}ms · same output: {String(data.measured.same_output)}</p>}
      <p className="muted">Complexity (estimate): {data.original_complexity?.time} / {data.original_complexity?.space} → {data.optimized_complexity?.time ?? "–"} / {data.optimized_complexity?.space ?? "–"}</p></div>
    <Diff original={code} changed={data.optimized_code} labels={["Original", "Optimized"]} />
    <button onClick={() => copy(data.optimized_code)}>Copy optimized code</button>
    <button onClick={() => onLoad(data.optimized_code)} disabled={v && !v.verified}>Replace editor contents</button></div>;
}
