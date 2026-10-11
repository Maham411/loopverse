"""Live check against the real Groq API (run on your own machine, needs internet).

    export GROQ_API_KEY=...        (Windows PowerShell: $env:GROQ_API_KEY="...")
    python tests/live_groq_check.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SMOGGUARD_LLM", "groq")
from smogguard.assistant import ask_detailed  # noqa: E402

QUESTIONS = [
    "Will schools in Gulberg close tomorrow?",
    "Kal Johar Town mein hawa kaisi hogi? Bachon ko school bhejein?",
    "What is the forecast for Karachi tomorrow?",
    "Any community tips from residents for smog at home?",
]
if not os.environ.get("GROQ_API_KEY"):
    sys.exit("Set GROQ_API_KEY first.")
ok = 0
for q in QUESTIONS:
    r, d = ask_detailed(q)
    ok += d["llm"].endswith("accepted")
    print(f"\nQ: {q}\nLLM: {d['llm']}\nforecast_called={r['forecast_called']} sources={r['sources']}\n{r['answer']}")
print(f"\n{ok}/{len(QUESTIONS)} answers rephrased by Groq and accepted by the validator "
      "(rejected or unavailable answers fall back to the grounded deterministic text).")
