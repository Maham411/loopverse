"""Answer a released question set in one go.

    python run_questions.py spec/25_unseen_questions.md          -> answers.json
    python run_questions.py questions.json --out my_answers.json

Accepted inputs: .json (list of strings or of {"question_id"/"id", "question"}),
.csv (columns question_id/id and question), or .md/.txt with one question per
line ("1. ...", "Q1: ...", "- ...", or markdown table rows "| Q1 | ... |").
"""
import argparse
import csv
import json
import re
from pathlib import Path

from smogguard.assistant import ask


def parse_questions(path):
    path = Path(path)
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() == ".json":
        data = json.loads(text)
        data = data.get("questions", data) if isinstance(data, dict) else data
        out = []
        for i, item in enumerate(data, 1):
            if isinstance(item, str):
                out.append((f"Q{i:02d}", item))
            else:
                out.append((str(item.get("question_id") or item.get("id") or f"Q{i:02d}"), item["question"]))
        return out
    if path.suffix.lower() == ".csv":
        rows = list(csv.DictReader(text.splitlines()))
        return [(str(r.get("question_id") or r.get("id") or f"Q{i:02d}"), r["question"]) for i, r in enumerate(rows, 1)]
    out = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or re.fullmatch(r"\|?[\s:|-]+\|?", s):
            continue
        m = re.match(r"^\|\s*(Q?\d+)\s*\|\s*(.+?)\s*\|", s)
        if m and not m.group(2).lower().startswith("question"):
            out.append((m.group(1), m.group(2)))
            continue
        m = re.match(r"^(?:\*\*)?(Q\s?\d+|\d+)(?:\*\*)?\s*[.):\-]\s*(?:\*\*)?\s*(.+)$", s, re.IGNORECASE)
        if m:
            qid = m.group(1).replace(" ", "").upper()
            out.append((qid if qid.startswith("Q") else f"Q{int(qid):02d}", m.group(2).strip("* ")))
            continue
        if s.startswith(("- ", "* ")):
            out.append((f"Q{len(out) + 1:02d}", s[2:].strip()))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("questions")
    ap.add_argument("--out", default="answers.json")
    args = ap.parse_args()
    qs = parse_questions(args.questions)
    answers = [ask(q, question_id=qid) for qid, q in qs]
    Path(args.out).write_text(json.dumps(answers, ensure_ascii=False, indent=2), encoding="utf-8")
    called = sum(a["forecast_called"] for a in answers)
    print(f"Answered {len(answers)} questions -> {args.out} (forecast called for {called})")
