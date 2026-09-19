"""Sample (bad): a validator with no failure path at all.

Every rule in a gate of this shape can only ever report success.
Expected: SFL-001.
"""

import json


def main():
    with open("records.json", encoding="utf-8") as fh:
        data = json.load(fh)
    for rec in data:
        print("%s: %s" % (rec["id"], rec["status"]))


main()
