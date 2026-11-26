// Line diff (LCS) with changed lines highlighted: used for original vs corrected/optimized code.
function diff(a, b) {
  const x = a.split("\n"), y = b.split("\n"), n = x.length, m = y.length;
  const L = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) L[i][j] = x[i] === y[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
  const out = []; let i = 0, j = 0;
  while (i < n && j < m) { if (x[i] === y[j]) { out.push(["same", x[i]]); i++; j++; } else if (L[i + 1][j] >= L[i][j + 1]) out.push(["del", x[i++]]); else out.push(["add", y[j++]]); }
  while (i < n) out.push(["del", x[i++]]); while (j < m) out.push(["add", y[j++]]);
  return out;
}
export default function Diff({ original, changed, labels = ["Original", "Changed"] }) {
  const rows = diff(original, changed);
  return <div><div className="muted">{labels[0]} (red = removed) → {labels[1]} (green = added)</div>
    <pre className="diff">{rows.map(([t, l], i) => <div key={i} className={"d-" + t}>{t === "add" ? "+ " : t === "del" ? "- " : "  "}{l}</div>)}</pre></div>;
}
