"""Sample (bad): counts failures, then never lets the count reach the exit code.

The report is honest. The exit code is always 0.
Expected: SFL-004 (and SFL-001, since there is no failure path at all).
"""


def check(items):
    problems = 0
    for item in items:
        if not item:
            problems += 1

    print("problems=%d" % problems)
    return 0


check([])
