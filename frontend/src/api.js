async function req(path, opts = {}) {
  try {
    const r = await fetch("/api" + path, opts);
    if ((r.headers.get("content-type") || "").includes("pdf")) return await r.blob();
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || "Request failed");
    return data;
  } catch (e) { throw new Error(e.message === "Failed to fetch" ? "Cannot reach the backend. Is Flask running on port 5000?" : e.message); }
}
const post = (p, body) => req(p, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
export const api = {
  languages: () => req("/languages"), health: () => req("/health"), nlpMetrics: () => req("/nlp/metrics"),
  run: (code, stdin, language) => post("/run", { code, stdin, language }),
  corrected: (code, error, language, stdin) => post("/corrected-code", { code, error, language, stdin }),
  optimize: (code, stdin, language) => post("/optimize", { code, stdin, language }),
  tests: (code, cases, language) => post("/tests", { code, cases, language }),
  genTests: (code, language) => post("/generate-tests", { code, language }),
  chat: (p) => post("/chat", p),
  report: (data) => post("/report", data),
  history: () => req("/history"), remove: (id) => req("/history/" + id, { method: "DELETE" }),
  upload: (file, language) => { const f = new FormData(); f.append("file", file); f.append("language", language); return req("/upload", { method: "POST", body: f }); },
};
