import { useState, useEffect } from "react";
import Editor from "./components/Editor.jsx";
import History from "./components/History.jsx";
import Chat from "./components/Chat.jsx";
import { Output, Errors, Complexity, Quality, Tests, Optimize } from "./components/Panels.jsx";
import { api } from "./api.js";

const SAMPLE = {
  python: "a = 10\nb = 5\nprint(a *== b)\n", c: '#include <stdio.h>\nint main() {\n  int a = 5\n  printf("%d\\n", a);\n  return 0;\n}\n',
  cpp: "#include <iostream>\nint main() {\n  std::cout << value;\n}\n", java: 'public class Main {\n  public static void main(String[] args) {\n    System.out.println("Hello");\n  }\n}\n',
  javascript: "const user = null;\nconsole.log(user.name);\n", html: "<div>\n<p>Hello\n</div>\n<img src=\"a.png\">\n",
  css: "body {\n  color red;\n  margin: 0\n  colour: blue;\n}\n", sql: "CREATE TABLE t(a INT);\nINSERT INTO t VALUES (1),(2);\nSELECT a FROM t WHERE a > 1;\n",
};
const TABS = ["Output", "Errors", "Complexity", "Quality", "Optimize", "Tests", "Chat"];

export default function App() {
  const [page, setPage] = useState("compiler"); const [language, setLanguage] = useState("python"); const [langs, setLangs] = useState([]);
  const [code, setCode] = useState(SAMPLE.python); const [stdin, setStdin] = useState("");
  const [r, setR] = useState(null); const [opt, setOpt] = useState(null); const [tab, setTab] = useState("Output"); const [loadedTests, setLoadedTests] = useState(null);
  const [busy, setBusy] = useState(false); const [err, setErr] = useState(""); const [dark, setDark] = useState(false);
  useEffect(() => { api.languages().then((d) => setLangs(d.languages)).catch((e) => setErr(e.message)); }, []);
  useEffect(() => { document.documentElement.dataset.theme = dark ? "dark" : "light"; }, [dark]);
  const cur = langs.find((l) => l.id === language);

  const changeLang = (id) => { setLanguage(id); setCode(SAMPLE[id] || ""); setR(null); setOpt(null); };
  const run = async (c = code) => {
    setBusy(true); setErr(""); setOpt(null);
    try { const res = await api.run(c, stdin, language); setR(res); setTab(res.error ? "Errors" : "Output"); } catch (e) { setErr(e.message); }
    setBusy(false);
  };
  const optimize = async () => { setTab("Optimize"); setBusy(true); setErr(""); setOpt(null); try { setOpt(await api.optimize(code, stdin, language)); } catch (e) { setErr(e.message); } setBusy(false); };
  const upload = async (e) => { const f = e.target.files[0]; if (!f) return; try { const d = await api.upload(f, language); setCode(d.code); setR(null); } catch (x) { setErr(x.message); } e.target.value = ""; };
  const download = async () => {
    try { const b = await api.report({ ...r, optimization: opt }); const a = document.createElement("a"); a.href = URL.createObjectURL(b); a.download = "codelens_report.pdf"; a.click(); } catch (e) { setErr(e.message); }
  };
  const load = (c) => { setCode(c); setR(null); setOpt(null); };

  return <div className="app">
    <header><h1>CodeLens AI</h1><nav>
      <button className={page === "compiler" ? "active" : ""} onClick={() => setPage("compiler")}>Compiler</button>
      <button className={page === "history" ? "active" : ""} onClick={() => setPage("history")}>History</button>
      <button onClick={() => setDark(!dark)} title="Toggle theme">{dark ? "☀ Light" : "🌙 Dark"}</button></nav></header>
    {err && <div className="banner" onClick={() => setErr("")}>{err} <small>(click to dismiss)</small></div>}
    {page === "history" ? <main className="single"><History onOpen={(c) => { load(c); setPage("compiler"); }} /></main> :
    <main className="grid">
      <section>
        <div className="toolbar">
          <select value={language} onChange={(e) => changeLang(e.target.value)} aria-label="Language">
            {langs.map((l) => <option key={l.id} value={l.id} disabled={!l.available}>{l.label}{l.available ? "" : " (not installed)"}</option>)}
            {!langs.length && <option value="python">Python</option>}</select>
          <label className="btn">Upload<input type="file" hidden onChange={upload} /></label>
          <button className="primary" onClick={() => run()} disabled={busy}>{busy ? "Working…" : "Run & Analyze"}</button>
          <button onClick={optimize} disabled={busy || ["html", "css"].includes(language)}>Optimize Code</button>
          <button onClick={download} disabled={!r}>Download Report</button>
        </div>
        {langs.some((l) => !l.available) && <p className="muted">Unavailable: {langs.filter((l) => !l.available).map((l) => `${l.label} (${l.install_hint})`).join(" · ")}</p>}
        {cur && <p className="muted">Isolation: {cur.isolation}{cur.can_run ? "" : " · validated, not executed"}</p>}
        <Editor value={code} onChange={setCode} errorLine={r?.error?.line} language={language} theme={dark ? "dark" : "light"} />
        {!["html", "css"].includes(language) && <textarea className="stdin" placeholder="Program input (one value per line)" value={stdin} onChange={(e) => setStdin(e.target.value)} />}
      </section>
      <section>
        <div className="tabs">{TABS.map((t) => <button key={t} className={tab === t ? "active" : ""} onClick={() => setTab(t)}>{t}{t === "Errors" && r?.error ? " ●" : ""}</button>)}</div>
        <div className="panel">
          {tab === "Output" && <Output r={r} />}
          {tab === "Errors" && <Errors r={r} code={code} language={language} stdin={stdin} onLoad={load} onRun={run} />}
          {tab === "Complexity" && <Complexity r={r} />}
          {tab === "Quality" && <Quality r={r} />}
          {tab === "Optimize" && <Optimize data={opt} busy={busy} code={code} language={language} onLoad={load} />}
          {tab === "Tests" && <Tests code={code} language={language} stdin={stdin} loaded={loadedTests} />}
          {tab === "Chat" && <Chat code={code} language={language} stdin={stdin} onLoad={load} onTests={(c) => { setLoadedTests(c); setTab("Tests"); }} />}
        </div>
        {r && !r.history_saved && <p className="muted">History not saved (MongoDB unavailable).</p>}
      </section>
    </main>}
  </div>;
}
