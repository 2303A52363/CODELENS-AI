import { useEffect, useState } from "react";
import { api } from "../api.js";
export default function History({ onOpen }) {
  const [d, setD] = useState(null); const [err, setErr] = useState("");
  const load = () => api.history().then(setD).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, []);
  if (err) return <p className="warn">{err}</p>; if (!d) return <p>Loading…</p>;
  if (!d.db_available) return <p className="warn">{d.message}</p>;
  if (!d.items.length) return <p className="muted">No saved submissions yet.</p>;
  return <div>{d.items.map((i) => <div className="card hist" key={i._id}>
    <div><b>{new Date(i.created_at).toLocaleString()}</b> · {i.error?.name || "no error"} · quality {i.quality?.score ?? "–"}<pre className="out">{i.code.slice(0, 160)}</pre></div>
    <div><button onClick={() => onOpen(i.code)}>Open</button><button onClick={async () => { await api.remove(i._id); load(); }}>Delete</button></div></div>)}</div>;
}
