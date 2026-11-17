#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""state-machine-negative-control.py -- gate 18: the artifact under test is
actually executed, and its negative control is shown to bite.

Why this gate exists
--------------------
On 2026-10-28 an independent review seat asked one question of this repository:
*do any of the seventeen gates ever execute `evidence-gated-state-machine/`?*

The answer, measured rather than estimated, was no. A static search for the
module name across every gate returned zero hits; a marker side effect planted in
the implementation was not observed by any of the fifteen non-byte gates; the one
gate whose name suggests otherwise (gate 13, `impl-mutation.py`) targets
`examples/S5-Qregister/implementation.py` and nothing else.

The consequence was demonstrated in the same session. The tree was at 17/17
green. `Registry.verify_chain()` -- the entire basis for the phrase "the audit
chain is verifiable" -- was replaced with an unconditional `return True`, and
`sh .githooks/pre-commit` still printed `all gates passed`. The repository's own
negative control, `demo_tamper_check.py`, failed on the same tree. So the
harness could see the defect and the gate list could not: **a change that hollows
out the verifier can be merged through the legal flow, and no gate ever says a
word.** That is this catalogue's own subject, one level up.

This gate is the answer. It does not re-check the implementation's correctness --
that is a different and larger piece of work, and where it is not done it is
declared below rather than implied. It checks the property the reviews turned
out to be missing: *the artifact is executed, and the check that is supposed to
watch it is not powerless.*

What it runs
------------
  P1  `evidence_gated_state_machine.py` exits 0. The demonstration itself runs.
  P2  `demo_tamper_check.py` exits 0. Tampering with a registered entity is
      detected, so the baseline is not already broken.
  P3  For each mutation in MUTATIONS: copy the artifact to a throw-away
      directory, apply the mutation there, run the negative control, and
      REQUIRE it to fail. A mutant that survives is a check that cannot see the
      shape it exists to catch, and the gate goes red.
  P4  Restore an unmutated copy and require the negative control to pass again.
      Without this a harness that rejects everything would satisfy P3 and be
      useless -- the "stuck red" discriminator the `negative-control` CI job
      already applies to the manifest gate.

The artifact under test is never modified: every mutation runs on a copy in
`tempfile.mkdtemp()`, and the copies are removed before the gate returns.

What this gate does NOT claim
-----------------------------
Printed by every run, and repeated here so that the limit survives being read out
of context. Three shapes were measured as **undetected by the current
implementation**, and this gate does not assert on them, because they are defects
in the artifact rather than in the harness, and fixing them is tracked separately:

  X1  deleting the last registered entity leaves `verify_chain()` True
      (`verify_chain` walks `self.entities`, never `self.chain`, so the chain
      length is not compared against the number of registration events)
  X2  `reg.chain.append("FORGED")` leaves `verify_chain()` True (same cause)
  X3  re-registering an entity after tampering it recomputes a consistent hash,
      so the tamper becomes invisible (no append-only record of prior hashes)

Being printed is the point. A gate that stayed silent about them would be the
failure it was written to catch; a gate that asserted on them would be red until
the implementation is fixed and would be switched off long before that. The
mutations below are the subset that the implementation *can* currently kill, so
the gate measures the harness, not the defect backlog.

Mutations asserted (each must be killed)
----------------------------------------
  M1  `verify_chain()` reduced to an unconditional `return True`. This is the
      exact edit that survived all seventeen gates on 2026-10-28 -- with one
      precision that matters and is easy to lose in the retelling: the byte gates
      (5 and 6) DO notice the edit, so the "legal flow" that produced an
      all-green tree included regenerating `manifest.sha256` afterwards, which is
      what this hook's own failure message tells the author to do. The blind spot
      was never "nobody noticed the bytes changed"; it was that **no gate asks
      what the code does**. Rebuilding the manifest is a sanctioned step, so the
      sanctioned flow erases the only signal, and the tree goes green with the
      verifier hollowed out.
  M2  `version` is dropped from the hashed payload on both sides (registration
      and verification), so in-place version tampering leaves a consistent hash.
      A single-site edit would break the baseline instead of the detector, which
      is the wrong reason to go red.

Usage
-----
  python tools/state-machine-negative-control.py
  python tools/state-machine-negative-control.py --selftest
  python tools/state-machine-negative-control.py --artifact-dir <dir>   (testing aid)

Exit code: 0 = the artifact runs and every mutation is killed and the restored
copy passes; 1 = anything else, including an artifact that is not there. A missing
gate script is a failure in this repository, never a skip.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

ARTIFACT_DIRNAME = "evidence-gated-state-machine"
IMPL = "evidence_gated_state_machine.py"
DEMO = "demo_tamper_check.py"

# Vectors measured as undetected by the implementation as it stands. Printed on
# every run; see the module docstring for why they are declared rather than
# asserted.
KNOWN_GAPS = (
    ("X1", "deleting the last registered entity leaves verify_chain() True"),
    ("X2", "reg.chain.append('FORGED') leaves verify_chain() True"),
    ("X3", "tamper + re-register recomputes a consistent hash (no prior-hash record)"),
)


def _verify_chain_to_true(src):
    """Replace the body of Registry.verify_chain with `return True`.

    Anchored on the `def verify_chain` line and consumed up to the next method or
    the end of the class, so it does not depend on the body's current contents.
    Raises if the method is not found, because a mutation that silently did not
    apply would make P3 pass for the wrong reason.
    """
    pattern = re.compile(
        r"(?m)^(    def verify_chain\(self\)[^\n]*\n)(.*?)(?=^    def |^class |\Z)",
        re.S,
    )
    if not pattern.search(src):
        raise RuntimeError("M1: Registry.verify_chain not found -- mutation not applied")
    return pattern.sub(lambda m: m.group(1) + "        return True\n\n", src, count=1)


def _drop_version_from_payload(src):
    """Drop `version` from the hashed payload in BOTH hashing sites.

    Both sides must change together. Changing only the registration site makes the
    baseline verification fail immediately, and the mutant would be reported as
    killed while what actually broke was the artifact, not the detector.
    """
    hits = 0
    for receiver in ("self.version", "e.version"):
        needle = '"version": %s,' % receiver
        if needle in src:
            src = src.replace(needle, '"version": "",')
            hits += 1
    if hits == 0:
        raise RuntimeError("M2: no hashed-payload `version` field found -- mutation not applied")
    return src


MUTATIONS = (
    ("M1", "verify_chain() -> unconditional return True", _verify_chain_to_true),
    ("M2", "version dropped from the hashed payload (both sites)", _drop_version_from_payload),
)


def _artifact_dir(argv):
    for i, arg in enumerate(argv[1:]):
        if arg == "--artifact-dir":
            if i + 2 >= len(argv):
                raise SystemExit("--artifact-dir needs a value")
            return os.path.abspath(argv[i + 2])
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, ARTIFACT_DIRNAME)


def _run_py(script, cwd):
    """Run `script` with this interpreter in `cwd`; return (code, combined output)."""
    try:
        proc = subprocess.Popen(
            [sys.executable, script],
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        out, _ = proc.communicate()
    except OSError as exc:
        return 127, "could not execute %s: %s" % (script, exc)
    return proc.returncode, out.decode("utf-8", "replace")


def _copy_artifact(src_dir, dst_dir):
    """Copy the .py files of the artifact into a fresh directory."""
    os.makedirs(dst_dir)
    for name in (IMPL, DEMO):
        shutil.copyfile(os.path.join(src_dir, name), os.path.join(dst_dir, name))


def _rmtree(path):
    for dirpath, dirnames, filenames in os.walk(path, topdown=False):
        for name in filenames:
            try:
                os.remove(os.path.join(dirpath, name))
            except OSError:
                pass
        for name in dirnames:
            try:
                os.rmdir(os.path.join(dirpath, name))
            except OSError:
                pass
    try:
        os.rmdir(path)
    except OSError:
        pass


def run_gate(artifact_dir):
    """Return the process exit code for the gate on `artifact_dir`."""
    failures = []

    print("== gate 18: state-machine negative control ==")
    print("   artifact: %s" % artifact_dir)

    # -- a gate whose script is absent is a failure, not a skip -----------------
    for name in (IMPL, DEMO):
        if not os.path.isfile(os.path.join(artifact_dir, name)):
            print("   MISSING  %s" % name)
            print("gate 18 FAILED: %s is not in %s. A gate that is not there is not a gate."
                  % (name, artifact_dir))
            return 1

    # -- P1: the demonstration itself runs -------------------------------------
    code, out = _run_py(IMPL, artifact_dir)
    if code == 0:
        print("   P1 self-check            exit 0")
    else:
        failures.append("P1: %s exited %d (the demonstration does not run)" % (IMPL, code))
        print("   P1 self-check            exit %d -- FAILED" % code)
        for line in out.strip().splitlines()[-6:]:
            print("       | %s" % line)

    # -- P2: the baseline negative control passes ------------------------------
    code, out = _run_py(DEMO, artifact_dir)
    baseline_ok = code == 0
    if baseline_ok:
        print("   P2 negative control      exit 0 (tampering detected)")
    else:
        failures.append("P2: %s exited %d on an unmutated tree (the control is already red)"
                        % (DEMO, code))
        print("   P2 negative control      exit %d -- FAILED" % code)

    # -- P3: every mutation must be killed -------------------------------------
    tmp = tempfile.mkdtemp(prefix="gate18-")
    try:
        for label, description, transform in MUTATIONS:
            work = os.path.join(tmp, label)
            _copy_artifact(artifact_dir, work)
            target = os.path.join(work, IMPL)
            try:
                with open(target, "r", encoding="utf-8", newline="") as fh:
                    src = fh.read()
                mutated = transform(src)
                with open(target, "w", encoding="utf-8", newline="") as fh:
                    fh.write(mutated)
            except (OSError, RuntimeError) as exc:
                failures.append("%s: mutation could not be applied (%s)" % (label, exc))
                print("   %-3s %-40s NOT APPLIED -- FAILED" % (label, description))
                continue

            code, out = _run_py(DEMO, work)
            if not baseline_ok:
                # The unmutated tree is already red, so this mutant's exit code
                # says nothing about the mutant: the control would have failed
                # anyway. Reporting "killed" here is the exact error this gate's
                # own M2 docstring warns about -- a mutant "killed" by a detector
                # that was already broken. Reported, not counted; P2 already
                # failed, so the gate is red regardless.
                print("   %-3s %-40s not attributable (baseline already red, exit %d)"
                      % (label, description, code))
                continue
            if code != 0:
                print("   %-3s %-40s killed (control exit %d)" % (label, description, code))
            else:
                failures.append(
                    "%s: %s SURVIVED -- the negative control exited 0 with the verifier "
                    "hollowed out; this is the 2026-10-28 shape" % (label, description))
                print("   %-3s %-40s SURVIVED (control exit 0) -- FAILED"
                      % (label, description))

        # -- P4: the restored copy must pass again ------------------------------
        if baseline_ok:
            restore = os.path.join(tmp, "restore")
            _copy_artifact(artifact_dir, restore)
            code, out = _run_py(DEMO, restore)
            if code == 0:
                print("   P4 restored copy         exit 0 (the gate is not simply always red)")
            else:
                failures.append("P4: the restored copy exited %d (stuck-red harness)" % code)
                print("   P4 restored copy         exit %d -- FAILED" % code)
    finally:
        _rmtree(tmp)

    # -- declared non-coverage, printed on every run ---------------------------
    print("   declared non-coverage (measured, not asserted -- see docstring):")
    for label, text in KNOWN_GAPS:
        print("       %-3s %s" % (label, text))

    print("")
    if failures:
        print("gate 18 FAILED: %d problem(s)" % len(failures))
        for f in failures:
            print("  - %s" % f)
        return 1
    print("gate 18 PASSED: artifact executed, %d/%d mutations killed, restored copy green"
          % (len(MUTATIONS), len(MUTATIONS)))
    return 0


def selftest():
    """Prove this gate can fail, and that it is not simply always red."""
    failures = []
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    artifact = os.path.join(root, ARTIFACT_DIRNAME)
    script = os.path.abspath(__file__)

    if not os.path.isdir(artifact):
        print("SELF-TEST FAILED: the artifact directory is not there, so the control "
              "cannot be built: %s" % artifact)
        return 1

    def gate_on(path):
        proc = subprocess.Popen([sys.executable, script, "--artifact-dir", path],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        out, _ = proc.communicate()
        return proc.returncode, out.decode("utf-8", "replace")

    tmp = tempfile.mkdtemp(prefix="gate18-selftest-")
    try:
        # -- positive control: the real artifact must pass the real gate --------
        code, out = gate_on(artifact)
        if code == 0:
            print("  + positive control        real artifact passed, exit 0")
        else:
            failures.append("positive control: the real artifact did NOT pass (exit %d)\n%s"
                            % (code, out.strip()))

        # -- negative control: a hollowed-out artifact must be rejected ---------
        hollow = os.path.join(tmp, "hollow")
        _copy_artifact(artifact, hollow)
        target = os.path.join(hollow, IMPL)
        with open(target, "r", encoding="utf-8", newline="") as fh:
            src = fh.read()
        with open(target, "w", encoding="utf-8", newline="") as fh:
            fh.write(_verify_chain_to_true(src))
        code, out = gate_on(hollow)
        rejected_for_the_right_reason = code != 0 and (
            "SURVIVED" in out or "P2: " in out or "P4: " in out)
        if rejected_for_the_right_reason:
            print("  + negative control        hollowed verifier rejected, exit %d" % code)
        else:
            failures.append("negative control: a `return True` verifier was NOT rejected "
                            "(exit %d)\n%s" % (code, out.strip()))

        # -- missing-file control: an absent demo must fail, not skip -----------
        partial = os.path.join(tmp, "partial")
        os.makedirs(partial)
        shutil.copyfile(os.path.join(artifact, IMPL), os.path.join(partial, IMPL))
        code, out = gate_on(partial)
        if code != 0 and "not a gate" in out:
            print("  + missing-file control    absent demo rejected, exit %d" % code)
        else:
            failures.append("missing-file control: an absent %s was NOT a failure "
                            "(exit %d)\n%s" % (DEMO, code, out.strip()))
    finally:
        _rmtree(tmp)

    print("")
    if failures:
        print("SELF-TEST FAILED: %d problem(s)" % len(failures))
        for f in failures:
            print("  - %s" % f)
        return 1
    print("SELF-TEST PASSED: real artifact green, hollowed verifier red, absent demo red")
    return 0


def main(argv):
    if "--selftest" in argv[1:]:
        return selftest()
    try:
        artifact = _artifact_dir(argv)
    except SystemExit as exc:
        print(str(exc))
        return 1
    return run_gate(artifact)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
