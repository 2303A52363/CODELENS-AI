"""Train + evaluate the intent classifier (TF-IDF + Logistic Regression).
Run:  python -m nlp.train      (from backend/)"""
import csv, json, os, re
import joblib, numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import train_test_split, cross_val_score, StratifiedKFold
from sklearn.pipeline import Pipeline, make_union
HERE = os.path.dirname(__file__)

def normalize(t): return re.sub(r"\s+", " ", re.sub(r"[^\w\s']", " ", t.lower())).strip()
def jaccard(a, b):
    a, b = set(a.split()), set(b.split()); return len(a & b) / max(1, len(a | b))
def build_pipeline():
    feats = make_union(TfidfVectorizer(preprocessor=normalize, ngram_range=(1, 2), sublinear_tf=True),
                       TfidfVectorizer(preprocessor=normalize, analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True))
    return Pipeline([("tfidf", feats), ("clf", LogisticRegression(C=30, max_iter=3000))])

# High-precision keyword rules used as an optional override on top of the ML model (reported separately).
RULES = [("explain_complexity", r"big\s*o\b|complexity|order of growth|asymptotic"),
         ("generate_tests", r"test cases?|unit tests?|edge cases?|test data|test suite|test scenarios?"),
         ("optimize_code", r"optimi[sz]e|speed up|faster|quicker|performance|too slow|efficien")]
def rule_intent(text):
    t = text.lower()
    for intent, pat in RULES:
        if re.search(pat, t): return intent
    return None
def hybrid(model, texts): return [rule_intent(t) or p for t, p in zip(texts, model.predict(texts))]

def main():
    rows = list(csv.DictReader(open(os.path.join(HERE, "dataset.csv"), encoding="utf-8")))
    seen, X, y = set(), [], []
    for r in rows:
        n = normalize(r["text"])
        if n in seen: continue
        seen.add(n); X.append(r["text"]); y.append(r["intent"])
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.25, stratify=y, random_state=42)
    # drop test sentences that are near-duplicates (token Jaccard >= 0.8) of a training sentence
    ntr = [normalize(t) for t in Xtr]; keep = [i for i, t in enumerate(Xte) if max(jaccard(normalize(t), a) for a in ntr) < 0.8]
    removed = len(Xte) - len(keep); Xte = [Xte[i] for i in keep]; yte = [yte[i] for i in keep]
    model = build_pipeline().fit(Xtr, ytr)
    pred = model.predict(Xte); labels = sorted(set(y))
    cv = cross_val_score(build_pipeline(), Xtr, ytr, cv=StratifiedKFold(4, shuffle=True, random_state=1))
    rep = classification_report(yte, pred, labels=labels, output_dict=True, zero_division=0)
    metrics = {"samples_total": len(X), "train": len(Xtr), "test": len(Xte), "near_duplicates_removed_from_test": removed,
               "accuracy": round(accuracy_score(yte, pred), 4), "cv_accuracy_train_mean": round(float(cv.mean()), 4),
               "macro_precision": round(rep["macro avg"]["precision"], 4), "macro_recall": round(rep["macro avg"]["recall"], 4),
               "macro_f1": round(rep["macro avg"]["f1-score"], 4), "per_class": {l: {k: round(rep[l][k], 3) for k in ("precision", "recall", "f1-score", "support")} for l in labels},
               "labels": labels, "confusion_matrix": confusion_matrix(yte, pred, labels=labels).tolist()}
    hp = hybrid(model, Xte); hrep = classification_report(yte, hp, labels=labels, output_dict=True, zero_division=0)
    metrics["hybrid_rules_plus_ml"] = {"accuracy": round(accuracy_score(yte, hp), 4), "macro_precision": round(hrep["macro avg"]["precision"], 4),
        "macro_recall": round(hrep["macro avg"]["recall"], 4), "macro_f1": round(hrep["macro avg"]["f1-score"], 4)}
    probs = model.predict_proba(Xte).max(axis=1); metrics["mean_confidence_correct"] = round(float(probs[np.array(pred) == np.array(yte)].mean()), 3)
    pr = np.array(pred); yt = np.array(yte)
    metrics["threshold_analysis"] = {str(t): {"coverage": round(float((probs >= t).mean()), 3), "accuracy_on_covered": round(float((pr[probs >= t] == yt[probs >= t]).mean()), 3) if (probs >= t).any() else None} for t in (0.3, 0.4, 0.45, 0.5, 0.6)}
    json.dump(metrics, open(os.path.join(HERE, "metrics.json"), "w"), indent=2)
    final = build_pipeline().fit(X, y)  # deployed model uses all data; metrics above are from the held-out split
    joblib.dump(final, os.path.join(HERE, "model.joblib"))
    print(json.dumps({k: v for k, v in metrics.items() if k not in ("per_class", "confusion_matrix")}, indent=1))
    print("Confusion matrix rows/cols:", labels)
    for l, row in zip(labels, metrics["confusion_matrix"]): print(f"{l:20s}", row)
if __name__ == "__main__":
    from nlp.train import main as _main  # import by module name so pickled functions resolve
    _main()
