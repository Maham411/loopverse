"""SPEC section 6 entry point.

    from ask import ask
    ask("Will schools in Gulberg close tomorrow?")
    -> {"question_id": ..., "answer": ..., "sources": [...], "forecast_called": bool}

Command line:  python ask.py "Kal DHA mein hawa kaisi hogi?"
"""
import json
import sys

from smogguard.assistant import ask  # noqa: F401  (re-exported)
from smogguard.forecast_tool import forecast  # noqa: F401  (SPEC section 5 tool)

if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or input("Question: ")
    print(json.dumps(ask(question), ensure_ascii=False, indent=2))
