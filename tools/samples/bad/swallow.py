"""Sample (bad): swallows every exception "for robustness".

The counter only ever rises for records that happened to be well-formed, and the
records that raised simply vanish from the denominator.
Expected: SFL-002.
"""


def audit(records):
    checked = 0
    for rec in records:
        try:
            if rec.get("ok"):
                checked += 1
        except Exception:
            pass
    return checked


audit([])
