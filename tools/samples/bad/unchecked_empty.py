"""Sample (bad): an empty input is treated as success.

The check has a failure path, but the one case that matters — nothing was loaded —
falls through to the success branch.
Expected: SFL-003.
"""


def check(items):
    if not items:
        print("nothing to check")
        return 0

    for item in items:
        if not item.get("id"):
            raise ValueError("missing id")
    return len(items)


check([])
