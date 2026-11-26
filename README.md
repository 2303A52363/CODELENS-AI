# AI-Based Code Review & Bug Detection System

React (Vite) + Flask + Python AST/Ruff/Radon + Gemini + MongoDB + ReportLab.
One compiler workspace: run, errors, complexity, quality, optimize, tests, chat, PDF report, history.

## Structure
```
backend/  app.py config.py requirements.txt .env.example
          services/ sandbox.py analyzer.py complexity.py quality.py ai.py db.py report.py
          tests/test_core.py
frontend/ package.json vite.config.js index.html src/{main.jsx,App.jsx,api.js,styles.css,components/*}
```

## 1. Install
Requires Python 3.10+ (Linux/macOS/WSL recommended), Node 18+.
```
cd backend && python -m venv venv && source venv/bin/activate && pip install -r requirements.txt
cp .env.example .env
cd ../frontend && npm install
```
## 2. Run
```
cd backend && python app.py          # http://localhost:5000
cd frontend && npm run dev           # http://localhost:5173 (proxies /api to Flask)
```
## 3. Gemini
Get a key at https://aistudio.google.com/apikey and set `GEMINI_API_KEY` in `backend/.env`.
Without a key the app still works: errors use built-in explanations; corrected code, optimization and chat show a clear "AI unavailable" message.

## 4. MongoDB
Install MongoDB Community (or `docker run -d -p 27017:27017 mongo`). Default `MONGO_URI=mongodb://localhost:27017`.
Collection `submissions` is created automatically. If MongoDB is down, the app works and says history is unavailable.

## 5. Secure execution
User code never runs in the Flask process; it runs in a separate Python process in a temp dir.
- `SANDBOX_MODE=local` (default): CPU/memory/file-size/fd rlimits, wall-clock timeout with process-group kill, empty environment, and an audit hook that blocks sockets, subprocess, os.system, exec/fork, deletes, and file access outside the temp dir. Linux/macOS only for rlimits. This is a good development guard, NOT a hardened boundary.
- `SANDBOX_MODE=docker` (recommended for demos/deployment): `docker run --network none --memory --cpus --pids-limit --read-only`. Needs Docker; `docker pull python:3.12-slim` first. (Not tested in my environment.)

## 6. Tests
```
cd backend && python -m pytest -q tests
```
Covers: correct code, syntax error, runtime error, division by zero, off-by-one logic hint, loops/complexity, exponential recursion, input, missing input, infinite loop timeout, empty/invalid submission, sandbox blocks (network, file read, os.system), memory limit, test-case checker, AI fallback, PDF report, upload validation.

## 7. Common problems
- "Cannot reach the backend": start Flask first (port 5000).
- Gemini errors: check key/model name in `.env`; model names change, set `GEMINI_MODEL`.
- History empty/unavailable: MongoDB not running.
- Every run times out or fails on Windows: use WSL or `SANDBOX_MODE=docker`.
- "Sandbox unavailable": Docker not installed/running in docker mode.

## Honest limitations
Complexity is a static estimate. Python only (add a runner to `sandbox.RUNNERS` for more languages). Gemini output is a suggestion; optimization is verified by output equality and timing, not guaranteed.


---
# CodeLens AI upgrade (multi-language, NLP model, verified corrections)

Everything above still applies. This section documents what was added. Setup for Windows is at the end.

## What is new
- **8 languages, each with its own validator**: Python (ast+Ruff+sandbox), C/C++ (gcc/g++ compile + run), Java (javac/java), JavaScript (`node --check` + run), HTML (structure + accessibility validator), CSS (brace/semicolon/property/duplicate validator), SQL (sqlglot parser + restricted in-memory SQLite). The dropdown is filled from `/api/languages`; a language whose toolchain is missing is shown as *not installed* with an install hint, and requests for it return a clear error instead of fake results.
- **Separate NLP model** (`backend/nlp/`): TF-IDF (word 1-2 grams + char 2-5 grams) + Logistic Regression (scikit-learn) classifying 8 intents. The chatbox runs it on every message and routes to the right component.
- **Verified corrections**: AI-corrected code is parsed/compiled/run by the real toolchain. It is only labelled *Verified* if that passes; otherwise it is labelled *Not verified* (one automatic retry feeds the failure back to Gemini). Original code is never overwritten without a click.
- **Gemini**: default model is now `gemini-3.5-flash` with fallbacks (`GEMINI_FALLBACK_MODELS`) because `gemini-2.5-flash` was scheduled for shutdown in Oct 2026. Invalid key, quota/rate limit, timeout, network and retired-model errors are reported with specific messages. Check Google's current model list and change `GEMINI_MODEL` in `.env` if needed.
- Deterministic syntax advice (e.g. `a *== b`, `if a = 10:`) that lists the possible intended fixes instead of guessing one.
- Test-case generation (AI suggests inputs; your program's real output is recorded; *you* supply expected values), side-by-side diff with changed lines highlighted, dark/light theme, chat with intent badge, copy buttons, Enter/Shift+Enter, clear.

## NLP methodology
Intents: explain_error, debug_code, correct_code, optimize_code, explain_complexity, generate_tests, explain_code, general_question.
1. `nlp/dataset.csv`: 248 hand-written sentences (written by the project author team/assistant, **not** collected from real users) across the 8 intents.
2. Normalise (lowercase, strip punctuation), drop duplicate sentences, stratified 75/25 split (seed 42), then remove any test sentence whose token-Jaccard similarity with a training sentence is >= 0.8 (removed: 0).
3. TF-IDF features -> Logistic Regression (C=30). Chosen over deep models because the dataset is small and the model must be explainable in a viva. Hyper-parameters were chosen by repeated cross-validation on the full dataset, which means the held-out numbers below are slightly optimistic.
4. Inference: `nlp/intent.py`. Confidence below 0.45 is "low confidence" and is treated as a general question. A few high-precision keyword rules (complexity / tests / optimize) override the ML prediction; metrics are reported with and without them.
5. Run `python -m nlp.train` to retrain; it rewrites `model.joblib` and `metrics.json`.

### Held-out results (from `nlp/metrics.json`, 62 test sentences, 186 train)
ML only: accuracy **0.6613**, macro precision 0.6711, macro recall 0.6654, macro F1 0.642 (4-fold CV on train: 0.634).
ML + rules: accuracy 0.6774, macro precision 0.6985, macro recall 0.6811, macro F1 0.6651.

| intent | precision | recall | F1 | support |
|---|---|---|---|---|
| correct_code | 0.636 | 0.875 | 0.737 | 8 |
| debug_code | 0.583 | 0.778 | 0.667 | 9 |
| explain_code | 1.0 | 0.429 | 0.6 | 7 |
| explain_complexity | 0.556 | 0.714 | 0.625 | 7 |
| explain_error | 0.778 | 0.778 | 0.778 | 9 |
| general_question | 0.625 | 0.625 | 0.625 | 8 |
| generate_tests | 0.857 | 1.0 | 0.923 | 6 |
| optimize_code | 0.333 | 0.125 | 0.182 | 8 |

Confusion matrix (rows = true, columns = predicted, order = ['correct_code', 'debug_code', 'explain_code', 'explain_complexity', 'explain_error', 'general_question', 'generate_tests', 'optimize_code']):
```
correct_code         [7, 0, 0, 0, 0, 0, 0, 1]
debug_code           [1, 7, 0, 0, 0, 0, 0, 1]
explain_code         [0, 2, 3, 1, 1, 0, 0, 0]
explain_complexity   [0, 0, 0, 5, 0, 2, 0, 0]
explain_error        [1, 0, 0, 0, 7, 1, 0, 0]
general_question     [1, 0, 0, 0, 1, 5, 1, 0]
generate_tests       [0, 0, 0, 0, 0, 0, 6, 0]
optimize_code        [1, 3, 0, 3, 0, 0, 0, 1]
```
**Honest assessment:** about two thirds accuracy is modest. The intents overlap in wording and the dataset is small, so the main way to improve it is more varied, real student questions. Do not present this model as highly accurate; present it as a working, evaluated baseline.

## Language support matrix (what was actually tested here)
| Language | Method | Executed | Tested in my environment |
|---|---|---|---|
| Python | ast, Ruff, traceback, rule hints, sandbox | yes | yes |
| C / C++ | gcc/g++ diagnostics, compile, run | yes | yes (gcc/g++ 's present) |
| Java | javac / java | yes | **no (no JDK there); tests skip automatically** |
| JavaScript | node --check, node | yes | yes |
| HTML / CSS | own validators | no | yes |
| SQL | sqlglot + SQLite (ATTACH/PRAGMA/extension loading denied, timeout) | yes | yes |

Big-O estimation and the quality score are implemented for **Python only**. For other languages the Complexity tab says so, and for HTML/CSS/SQL explains why Big-O does not apply. Asking the chat for a non-Python complexity gives a Gemini estimate that is labelled as an estimate.

## Security notes and limits
Python runs in a separate process with rlimits, timeout, empty environment and an audit hook (no sockets/subprocess/outside-file access). **C, C++, Java and JavaScript run in a separate process with CPU/file limits and a timeout only: they are NOT network- or filesystem-isolated.** On Windows the rlimits are unavailable (timeout still applies). For a demo with untrusted users use Docker (`SANDBOX_MODE=docker` covers Python only in this version) or WSL, and say so honestly in the viva.

## API additions
`GET /api/languages`, `GET /api/health`, `POST /api/nlp/classify {text}`, `GET /api/nlp/metrics`, `POST /api/generate-tests`, and `language` fields on `/api/run`, `/api/corrected-code`, `/api/optimize`, `/api/tests`, `/api/chat`, `/api/upload`. `/api/chat` returns `{reply, intent:{intent,confidence,low_confidence,top3,line}, ai, action, error}`.

## Tests
`cd backend && python -m pytest -q tests`. Gemini itself is **not** called by the tests (no key); tests mock the Gemini transport to verify OUR pipeline (verification gate, routing, error mapping). Real Gemini output must be checked manually with your key.

## Known limitations
- Real Gemini calls, MongoDB history, Docker mode, Java, PowerShell script and the browser UI were not exercised in my environment.
- Gemini model names change; verify `GEMINI_MODEL`.
- C/C++/Java runtime errors get coarse classification; Java class detection is heuristic.
- CSS validator uses a limited property list and no at-rule/nesting support; HTML validator is not a full spec validator.
- Complexity is heuristic. The quality formula is project-specific.
- The sidebar dashboard layout from the brief is not built; the UI is a single workspace with tabs.

## Windows 11 setup (PowerShell)
1. Install: Python 3.11+ (tick "Add to PATH"), Node LTS, optional MSYS2/MinGW-w64 (gcc, g++) and JDK 17 (`winget install Python.Python.3.12 OpenJS.NodeJS.LTS EclipseAdoptium.Temurin.17.JDK`). Verify: `python --version`, `node -v`, `gcc --version`, `javac -version`.
2. One command: `powershell -ExecutionPolicy Bypass -File .\start.ps1` (checks tools, creates venv, installs, trains the NLP model if missing, starts both servers). Then open http://localhost:5173.
3. Manual: see the first part of this README. Put `GEMINI_API_KEY` in `backend/.env`.
