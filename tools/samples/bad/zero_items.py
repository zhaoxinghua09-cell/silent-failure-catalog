"""Sample (bad): trusts a test runner's exit code without checking that it collected
anything.

`pytest` reports success on an empty collection in many configurations, so this
wrapper is green when the suite ran nothing.
Expected: SFL-005.
"""

import subprocess
import sys


def main():
    proc = subprocess.run(
        ["pytest", "tests/", "-q"], capture_output=True, text=True
    )
    print(proc.stdout)
    sys.exit(proc.returncode)


main()
