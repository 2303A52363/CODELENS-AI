import { useState, useRef, useEffect } from "react";
import { api } from "../api.js";
const INTENT = { explain_error: "Explain error", debug_code: "Debug code", correct_code: "Correct code", optimize_code: "Optimize", explain_complexity: "Complexity", generate_tests: "Test cases", explain_code: "Explain code", general_question: "General question" };
function Rich({ text }) {  // renders ```fenced``` code blocks with a copy button
  return text.split(/```/).map((part, i) => {
    if (i % 2 === 0) return <span key={i} style={{ whiteSpace: "pre-wrap" }}>{part}</span>;
    const code = part.replace(/^[\w+-]*\n/, "");
    return <div key={i} className="codeblock"><button onClick={() => navigator.clipboard?.writeText(code)}>Copy</button><pre>{code}</pre></div>;
  });
}
export default function Chat({ code, language, stdin, onLoad, onTests }) {
  const [msgs, setMsgs] = useState([]); const [text, setText] = useState(""); const [busy, setBusy] = useState(false); const end = useRef();
  useEffect(() => {
    end.current?.scrollIntoView({ block: "nearest" });
  }, [msgs, busy]);
  const send = async () => {
    const msg = text.trim(); if (!msg || busy) return;
    const next = [...msgs, { role: "student", text: msg }]; setMsgs(next); setText(""); setBusy(true);
    try {
      const r = await api.chat({ message: msg, code, language, stdin, history: msgs.map((m) => ({ role: m.role, text: m.text })) });
      setMsgs([...next, { role: "tutor", text: r.reply || r.error || "No answer.", error: !r.reply, intent: r.intent, ai: r.ai, action: r.action }]);
    } catch (e) { setMsgs([...next, { role: "tutor", text: e.message, error: true }]); }
    setBusy(false);
  };
  return <div className="chatbox">
    <div className="chat">{msgs.length === 0 && <p className="muted">Ask about your code: “Why am I getting this error?”, “Fix my code”, “Make it faster”, “Explain line 3”, “Generate test cases”, “What is the time complexity?”</p>}
      {msgs.map((m, i) => <div key={i} className={"msg " + m.role + (m.error ? " bad" : "")}>
        <div className="who">{m.role}{m.intent && <span className="tag" title={`NLP confidence ${m.intent.confidence}${m.intent.low_confidence ? " (low – treated as general question)" : ""}`}>{INTENT[m.intent.intent]} · {Math.round(m.intent.confidence * 100)}%</span>}
          {m.role === "tutor" && !m.error && <span className="tag">{m.ai ? "Gemini" : "local"}</span>}</div>
        <Rich text={m.text} />
        {m.role === "tutor" && !m.error && <div><button onClick={() => navigator.clipboard?.writeText(m.text)}>Copy reply</button>
          {m.action?.code && <button onClick={() => onLoad(m.action.code)} disabled={!m.action.verified} title={m.action.verified ? "" : "Only verified code can replace the editor from here; see Errors tab to review it"}>Replace editor{m.action.verified ? "" : " (unverified)"}</button>}
          {m.action?.cases && <button onClick={() => onTests(m.action.cases)}>Load into Tests tab</button>}</div>}</div>)}
      {busy && <div className="msg tutor"><span className="muted">Thinking…</span></div>}<div ref={end} /></div>
    <textarea value={text} rows={2} onChange={(e) => setText(e.target.value)} placeholder="Ask about your code… (Enter to send, Shift+Enter for a new line)"
      onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }} />
    <button className="primary" onClick={send} disabled={busy || !text.trim()}>{busy ? "…" : "Send"}</button>
    <button onClick={() => setMsgs([])} disabled={!msgs.length}>Clear</button>
  </div>;
}
