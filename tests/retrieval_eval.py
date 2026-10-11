"""Retrieval quality check: expected document must be cited; no unrelated documents.

Run:  python tests/retrieval_eval.py
Each case: (question, required doc ids, allowed doc ids).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from smogguard.assistant import ask  # noqa: E402

CASES = [
    ("What should children do when smog is hazardous?", {"DOC-11"}, {"DOC-11", "DOC-01", "DOC-09", "DOC-03"}),
    ("At what PM2.5 level do schools close in Punjab?", {"DOC-03"}, {"DOC-03"}),
    ("When do schools switch to half day timing?", {"DOC-03"}, {"DOC-03"}),
    ("Do schools still close only when PM2.5 exceeds 300 for two days?", {"DOC-03"}, {"DOC-03"}),
    ("What is the odd-even rule for cars?", {"DOC-05"}, {"DOC-05", "DOC-10"}),
    ("Are ambulances exempt from the odd even restriction?", {"DOC-05"}, {"DOC-05"}),
    ("Are brick kilns allowed to operate during smog alerts?", {"DOC-08"}, {"DOC-08"}),
    ("Is burning crop residue allowed in the city?", {"DOC-08"}, {"DOC-08", "DOC-04"}),
    ("What are hospital OPD hours during hazardous smog days?", {"DOC-09"}, {"DOC-09"}),
    ("Where can my child get free nebulization?", {"DOC-09"}, {"DOC-09", "DOC-11"}),
    ("Does the Orange Line run more often during smog?", {"DOC-10"}, {"DOC-10"}),
    ("Where are the park-and-ride points?", {"DOC-10"}, {"DOC-10"}),
    ("Are bus fares higher during smog alerts?", {"DOC-10"}, {"DOC-10"}),
    ("What should elderly people with heart disease do?", {"DOC-11"}, {"DOC-11", "DOC-01"}),
    ("Advice for pregnant women during smog", {"DOC-11"}, {"DOC-11", "DOC-01"}),
    ("Which mask should I wear?", {"DOC-12"}, {"DOC-12", "DOC-01"}),
    ("Do surgical masks work against PM2.5?", {"DOC-12"}, {"DOC-12", "DOC-01"}),
    ("Do air purifiers help?", {"DOC-04"}, {"DOC-04", "DOC-12", "DOC-01"}),
    ("What is PM2.5?", {"DOC-04"}, {"DOC-04"}),
    ("What is the difference between AQI and PM2.5?", {"DOC-04"}, {"DOC-04", "DOC-06"}),
    ("Why is smog worse from October to December?", {"DOC-04"}, {"DOC-04"}),
    ("Who issues official smog alerts?", {"DOC-04"}, {"DOC-04"}),
    ("Is it safe to exercise outdoors during smog?", {"DOC-04"}, {"DOC-04", "DOC-01", "DOC-11"}),
    ("What does -999 mean in the sensor data?", {"DOC-06"}, {"DOC-06"}),
    ("Which areas does the system cover?", {"DOC-13"}, {"DOC-13", "DOC-06"}),
    ("Any home remedies like indoor plants for smog?", {"DOC-07"}, {"DOC-07", "DOC-12", "DOC-04"}),
    ("Should I keep my windows closed during smog?", {"DOC-01"}, {"DOC-01", "DOC-12", "DOC-07"}),
    ("What should people with asthma do?", {"DOC-11"}, {"DOC-11", "DOC-01"}),
    ("What are the rules for construction dust?", {"DOC-08"}, {"DOC-08"}),
    ("Bachon ke liye smog mein kya ehtiyat karein?", {"DOC-11"}, {"DOC-11", "DOC-01", "DOC-09"}),
    ("Gari ka odd even qanoon kya hai?", {"DOC-05"}, {"DOC-05", "DOC-10"}),
    ("School kab band hote hain?", {"DOC-03"}, {"DOC-03"}),
    ("Konsa mask pehnna chahiye?", {"DOC-12"}, {"DOC-12", "DOC-01"}),
    ("Hospital mein OPD kab tak khula hai?", {"DOC-09"}, {"DOC-09"}),
    ("Buzurgon ko smog mein kya karna chahiye?", {"DOC-11"}, {"DOC-11", "DOC-01"}),
]


def run(verbose=True):
    hit = clean = 0
    for q, need, allowed in CASES:
        r = ask(q)
        src = set(r["sources"])
        ok_hit, ok_clean = need <= src, src <= allowed
        hit += ok_hit
        clean += ok_clean
        if verbose and not (ok_hit and ok_clean):
            print(f"[{'HIT ' if ok_hit else 'MISS'}|{'CLEAN' if ok_clean else 'NOISY'}] {q} -> {r['sources']}")
    n = len(CASES)
    print(f"required doc cited: {hit}/{n}   no unrelated docs: {clean}/{n}")
    return hit, clean, n


if __name__ == "__main__":
    h, c, n = run()
    sys.exit(0 if h == n else 1)
