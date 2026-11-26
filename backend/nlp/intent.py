"""Inference wrapper. Loads the trained model (trains it first if missing)."""
import os, re
import joblib
from nlp import train
HERE = os.path.dirname(__file__); PATH = os.path.join(HERE, "model.joblib")
THRESHOLD = float(os.getenv("NLP_CONFIDENCE_THRESHOLD", "0.45")); _m = None
ORD = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10}
def _model():
    global _m
    if _m is None:
        if not os.path.exists(PATH): train.main()
        _m = joblib.load(PATH)
    return _m
def extract_line(text):
    t = text.lower(); m = re.search(r"line\s*(\d+)", t) or re.search(r"(\d+)(?:st|nd|rd|th)\s+line", t)
    if m: return int(m.group(1))
    m = re.search(r"(" + "|".join(ORD) + r")\s+(?:line|statement)", t)
    return ORD[m.group(1)] if m else None
def classify(text):
    m = _model(); p = m.predict_proba([text])[0]; order = p.argsort()[::-1]; cls = m.classes_
    top = [{"intent": cls[i], "confidence": round(float(p[i]), 3)} for i in order[:3]]
    rule = train.rule_intent(text); low = top[0]["confidence"] < THRESHOLD and rule is None
    return {"intent": rule or ("general_question" if low else top[0]["intent"]), "rule_override": rule is not None, "confidence": top[0]["confidence"], "low_confidence": low,
            "top3": top, "line": extract_line(text)}
