from retrieval_eval import CASES, run


def test_retrieval_quality():
    hit, clean, n = run(verbose=True)
    assert n == len(CASES) and hit == n and clean >= n - 1
