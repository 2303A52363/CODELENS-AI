
"""Gemini integration. API key stays server-side.
Every call returns (data, error_message).
"""

import json
import time
import requests
import config

from services import analyzer


URL = "https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent"

CONNECT_TIMEOUT = 10
READ_TIMEOUT = 90


def available():
    return bool(config.GEMINI_API_KEY)


def _http_msg(code):
    return {
        400: "Gemini rejected the request. Check the request and model.",
        401: "Invalid Gemini API key.",
        403: "Gemini API key is invalid or lacks permission.",
        404: "Gemini model not found or retired.",
        429: "Gemini quota or rate limit reached. Try again later.",
        500: "Gemini encountered an internal server error.",
        503: "Gemini servers are temporarily overloaded. Please try again."
    }.get(code, f"Gemini service error ({code}).")


def _call(prompt, system, as_json=True):

    if not available():
        return None, (
            "Gemini API key is not configured. "
            "Set GEMINI_API_KEY in backend/.env."
        )

    body = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}]
            }
        ],
        "systemInstruction": {
            "parts": [{"text": system}]
        },
        "generationConfig": {
            "temperature": 0.2
        }
    }

    if as_json:
        body["generationConfig"]["responseMimeType"] = "application/json"

    models = list(dict.fromkeys(
        [config.GEMINI_MODEL] + config.GEMINI_FALLBACK_MODELS
    ))

    errors = []

    for model in models:

        for attempt in range(2):

            try:
                response = requests.post(
                    URL.format(m=model),
                    json=body,
                    headers={
                        "x-goog-api-key": config.GEMINI_API_KEY
                    },
                    timeout=(CONNECT_TIMEOUT, READ_TIMEOUT)
                )

                if response.status_code == 404:
                    errors.append(f"{model}: model not found.")
                    break

                if response.status_code in (429, 500, 503):
                    errors.append(
                        f"{model}: {_http_msg(response.status_code)}"
                    )

                    if attempt == 0 and response.status_code in (500, 503):
                        time.sleep(2)
                        continue

                    break

                if response.status_code != 200:
                    return None, _http_msg(response.status_code)

                result = response.json()

                candidates = result.get("candidates", [])

                if not candidates:
                    errors.append(
                        f"{model}: Gemini returned no response."
                    )
                    break

                candidate = candidates[0]

                finish_reason = candidate.get("finishReason", "")

                if finish_reason == "MAX_TOKENS":
                    errors.append(
                        f"{model}: Response was too long. "
                        "Try with a smaller code sample."
                    )
                    break

                parts = candidate.get("content", {}).get("parts", [])

                text = "".join(
                    part.get("text", "")
                    for part in parts
                    if "text" in part
                ).strip()

                if not text:
                    errors.append(
                        f"{model}: Gemini returned an empty response."
                    )
                    break

                if as_json:
                    text = (
                        text.removeprefix("```json")
                        .removeprefix("```")
                        .removesuffix("```")
                        .strip()
                    )

                    return json.loads(text), None

                return text, None

            except requests.Timeout:
                errors.append(
                    f"{model}: Request timed out after "
                    f"{READ_TIMEOUT} seconds."
                )
                break

            except requests.ConnectionError:
                return None, (
                    "Cannot reach Gemini. Check your internet connection."
                )

            except requests.RequestException as exc:
                errors.append(f"{model}: Network request failed: {exc}")
                break

            except (KeyError, IndexError, ValueError, TypeError):
                errors.append(
                    f"{model}: Gemini returned an unexpected response."
                )
                break

    return None, (
        "Gemini could not complete the request. "
        + " ".join(errors)
        if errors else "Gemini is currently unavailable."
    )


TUTOR = (
    "You are a patient programming tutor for beginners. "
    "Be concise, accurate and simple. Never contradict verified facts. "
    "Never invent error locations."
)


def explain_error(code, err, lang="python"):

    fb = analyzer.kb_explanation(err["name"])

    p = (
        f"Language: {lang}. Detected deterministically (do not change): "
        f"error={err['name']}, type={err['type']}, "
        f"line={err.get('line')}, "
        f"line_text={err.get('code_line')!r}, "
        f"message={err.get('message')!r}.\n"
        f"Code:\n{code}\n\n"
        'Return JSON: {"what":str,"why":str,"fix":str,'
        '"steps":[str,...],"learn":str}. '
        "Steps must be short, ordered and specific to this error. "
        "Do not include the complete corrected program."
    )

    data, error = _call(p, TUTOR)

    if (
        isinstance(data, dict)
        and all(k in data for k in ("what", "why", "fix", "steps", "learn"))
    ):
        return {**data, "ai": True}

    return {
        **fb,
        "ai": False,
        "ai_note": error or "Showing built-in explanation."
    }


def corrected_code(code, err, lang="python", previous_failure=None):

    p = (
        f"Fix this {lang} program.\n"
        f"Detected problem: {err}.\n"
        + (
            f"Previous correction failed validation: {previous_failure}\n"
            if previous_failure else ""
        )
        + f"\nOriginal code:\n{code}\n\n"
        "Return the COMPLETE corrected program, not just changed lines. "
        "Preserve the original intended behaviour. "
        "Keep unrelated code and change only what is necessary. "
        "Do not omit imports, functions or required statements. "
        'Return JSON: {"corrected_code":str,"changes":[str,...]}'
    )

    data, error = _call(p, TUTOR)

    if (
        isinstance(data, dict)
        and isinstance(data.get("corrected_code"), str)
        and data["corrected_code"].strip()
    ):
        return {**data, "ai": True}

    return {
        "ai": False,
        "error": error or "Gemini returned an unexpected format."
    }


def optimize(code, lang="python"):

    p = (
        f"Review this {lang} code for efficiency. "
        f"It may already be bug-free.\n"
        f"Code:\n{code}\n\n"
        "Return complete optimized code. "
        "Preserve identical behaviour and output. "
        "Do not remove required functionality. "
        "If nothing meaningful can be improved, return the original code. "
        'Return JSON: {"issues":[{"line":int,"problem":str,'
        '"why_it_matters":str}],"optimized_code":str,"summary":str}.'
    )

    data, error = _call(p, TUTOR)

    if (
        isinstance(data, dict)
        and isinstance(data.get("optimized_code"), str)
        and data["optimized_code"].strip()
    ):
        return {**data, "ai": True}

    return {
        "ai": False,
        "error": error or "Gemini returned an unexpected format."
    }


def generate_tests(code, lang="python"):

    p = (
        f"Suggest test inputs for this {lang} program.\n"
        f"Code:\n{code}\n\n"
        "Include normal, boundary, edge and invalid cases. "
        "Programs read from stdin, so input is the exact stdin text. "
        'Return JSON: {"cases":[{"category":"normal|boundary|edge|invalid",'
        '"input":str,"description":str}]}. '
        "Return at most 8 cases. Do not guess outputs."
    )

    data, error = _call(p, TUTOR)

    if isinstance(data, dict) and isinstance(data.get("cases"), list):
        return {
            "cases": data["cases"][:8],
            "ai": True
        }

    return {
        "cases": [],
        "ai": False,
        "error": error or "Gemini returned an unexpected format."
    }


def chat(code, history, message, lang="python", facts="", intent=""):

    convo = "\n".join(
        f"{m.get('role')}: {m.get('text')}"
        for m in history[-8:]
    )

    p = (
        f"Language: {lang}. "
        f"Student intent classified by NLP: {intent}.\n"
        f"Verified analysis facts:\n{facts or 'none'}\n\n"
        f"Student's current code:\n{code}\n\n"
        f"Conversation:\n{convo}\n"
        f"Student: {message}\n\n"
        "Answer helpfully and briefly. "
        "Use Markdown code fences for code. "
        "Teach; do not dump a full solution unless requested."
    )

    reply, error = _call(p, TUTOR, as_json=False)

    if reply:
        return {
            "reply": reply,
            "ai": True
        }

    return {
        "reply": None,
        "ai": False,
        "error": error
    }

