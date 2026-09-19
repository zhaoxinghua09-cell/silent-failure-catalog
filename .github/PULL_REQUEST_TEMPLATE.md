# Pull request

## What this changes

<!-- One or two sentences. If it adds an entry, name it. If it fixes a tool, say which rule and which direction (false positive / false negative). -->

## The four gates

Run all four locally. Paste the output of the last one — CI runs the same set, and a pull request that fails here will fail there.

```bash
python tools/gate-lint.py --selftest
python tools/check-catalog.py --selftest
python tools/check-catalog.py --scan-leaks
python tools/make-manifest.py --check
```

- [ ] `gate-lint.py --selftest` — exits 0
- [ ] `check-catalog.py --selftest` — exits 0
- [ ] `check-catalog.py --scan-leaks` — exits 0, or every remaining hit is a real finding I have explained below
- [ ] `make-manifest.py --check` — exits 0 after I ran `python tools/make-manifest.py`

## If this adds or changes a catalog entry

- [ ] A new entry uses the next free `SF-nnn` and the file name starts with it
- [ ] All six sections are present — `Symptom`, `Why it is silent`, `Minimal reproduction`, `Self-check`, `Fix`, `Related`
- [ ] The `Fix` section carries a negative-control table
- [ ] The entry is linked from `failures/README.md`, the taxonomy table in `README.md`, `llms.txt` and `docs/start-here.md`
- [ ] `CHANGELOG.md` has a line under `Unreleased`

## If this changes a detection rule

- [ ] The rule declares its confidence level and its known false positives, in the source
- [ ] There is a sample pair: one file under `tools/samples/bad/` it must flag, one under `tools/samples/good/` it must not
- [ ] `--selftest` fails when I deliberately invert one of those samples *(that is the point of the sample pair — state that you checked it)*

## Negative control

<!-- Every non-trivial change here needs one. What did you break on purpose, and what did the check do when you broke it? "It passed" is not an answer; the relevant answer is "it failed, as required". -->

## De-identification

- [ ] No client, employer or vendor names
- [ ] No internal hostnames, URLs or ticket ids
- [ ] No absolute local paths
- [ ] No real account ids, tokens or personal data
- [ ] Placeholders are written without an `@` (so `name [at] example.invalid`), because a scanner that fires on placeholders trains people to ignore it

## Scope

- [ ] The failure is **silent**, not loud
- [ ] It is one failure mode, not two
- [ ] No vendor claim and no standard-conformance claim is made
- [ ] I did not add an "awesome list" or a set of outbound links outside `docs/where-to-find-us.md`
