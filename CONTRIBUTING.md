# Contributing

Thanks for wanting to add to the catalog. The bar is deliberately specific, because the whole value of this repo is that its entries are **falsifiable**.

## An entry is accepted when it has all four

| # | Requirement | Why |
|---|---|---|
| 1 | **A name** | An unnamed phenomenon cannot be searched for or cited |
| 2 | **A minimal reproduction** | Runnable, or clearly marked illustrative. Prose alone is an anecdote |
| 3 | **A fix** | The concrete change that turns a silent pass into a loud failure |
| 4 | **A negative control** | Proof the fix fails when the thing it guards is broken |

Missing #4 is the most common reason for rejection. "Add a check" is not a fix. "Add a check, and here is the broken input that now makes it fail" is a fix.

## An entry is rejected when

- The failure is **loud** (crash, traceback, non-zero exit, alert). That is an ordinary bug — this catalog is specifically about failures that wear the costume of success.
- It is **vendor-specific**. "Tool X does this" is not a pattern; it is a bug report. Rewrite it as the pattern the tool demonstrated.
- It **claims conformance** with a standard without quoting a normative clause.
- It is **two failure modes in one file**. Split it.

## Process

```bash
cp failures/TEMPLATE.md failures/SF-<next-number>-<slug>.md
# fill in every section — empty sections fail validation
python tools/check-catalog.py     # must exit 0
```

Then update, in the same commit:

1. `failures/README.md` — the index table
2. `README.md` — the taxonomy table
3. `llms.txt` — the entry list
4. `docs/start-here.md` — symptom → entry
5. `CHANGELOG.md` — one line under `Unreleased`
6. `manifest.sha256` and `INTEGRITY.md` — run `python tools/make-manifest.py`

Pull requests that add an entry without updating items 1–4 and 6 will fail CI. Item 5 is the exception: `check_changelog` in `tools/check-catalog.py` verifies only that `CHANGELOG.md` exists and carries a semantic version, so a missing `Unreleased` line is not caught mechanically — that one is a manual discipline, and saying otherwise would be exactly the kind of over-claim this catalog records.

If you are not sure you have a pattern yet — symptoms without a reproduction are still worth reporting — read [`SUPPORT.md`](SUPPORT.md) first. And if you would rather attack the tooling than extend the catalog, [`docs/take-the-challenge.md`](docs/take-the-challenge.md) has three tiers for that, starting at five minutes.

### On outbound links

Links to our own channels are permitted **only** in `docs/where-to-find-us.md` and `docs/start-here.md`. Anywhere else they are a validation failure. The rule is machine-checked (`check_promo_links` in `tools/check-catalog.py`) rather than requested politely, because a guideline with no detector has never been observed failing — which, by this catalog's own rule 2, makes it not a guideline.

### Why step 4 is required

`INTEGRITY.md` records a SHA-256 per file. Editing any content file invalidates it. A manifest that is allowed to drift is worse than no manifest at all, because a reader will treat it as evidence — so CI rebuilds nothing and simply requires the committed manifest to match the tree. Regenerating is one command; forgetting it is a red build with an exact list of what changed.

The manifest also has a **negative control in CI**: one byte is appended to a file on purpose, and the verification is *required* to fail. A verifier that cannot fail is the subject of this catalog, not an exception to it.

## Numbering

`SF-nnn` is **append-only and permanent**.

- Next number = highest existing + 1. Never reuse, never renumber.
- To retire an entry: set `**Status**: deprecated`, add `**Superseded by**: SF-nnn`, and keep the file online. Removing a file breaks every citation that points at it.

## De-identification

Entries are often written up from real incidents. **Generalize before committing.**

Remove, without exception:

| Remove | Replace with |
|---|---|
| Client, employer and vendor names | "a service", "the tool" |
| Internal hostnames, URLs, ticket ids | `example.internal`, `TICKET-000` |
| Absolute local paths (a drive-letter path, or an absolute home path) | `path/to/file` |
| Real account ids, emails, tokens, keys | `example.invalid`, `<redacted>` |
| Named individuals | "the author", "the operator" |
| Business-specific numbers (revenue, counts, traffic) | orders of magnitude, or omit |

> On using `example.invalid`: it is a reserved TLD (RFC 2606) that can never be registered, so it is the correct placeholder for a host or address. Write it **without** an `@` — a string shaped like a real address trips secrets scanners, and a scanner that fires on placeholders trains people to ignore it. De-identify the content; do not add a whitelist.

A quick check before you commit:

```bash
python tools/check-catalog.py --scan-leaks
```

This is a heuristic scan (paths, emails, hostnames, key-shaped strings). It has false positives and **does not replace reading your own diff**. Passing the scan is not a guarantee of de-identification.

When a line must contain a pattern-like string — for example, this file used to spell out a literal absolute path while explaining that absolute paths must be removed — add an inline allowance:

```markdown
C:\Users\<name>\...   <!-- leak-scan: allow -->
```

Allowances are **counted and printed**, never silent. A suppression that leaves no trace is the failure mode this catalog documents.

## Writing style

- **Lead with the symptom**, not the background. Someone arrives here from a search engine at the symptom.
- **Be concrete.** Line numbers, exit codes, exact strings. Vague entries cannot be verified.
- **State confidence honestly.** If a detection heuristic has false positives, say which ones.
- English is primary. A short `中文要点` block at the end of an entry is welcome; a full translation is not required.

## Adding a detection rule to `tools/`

- Parse with `ast`. Do not regex Python source you can parse.
- Declare `confidence` (`high` / `medium` / `low`) and document known false positives in the rule's docstring.
- Ship a sample pair in `tools/samples/bad/` and `tools/samples/good/`. `python tools/gate-lint.py --selftest` runs them; a rule whose samples fail is not merged.
- No third-party dependencies.
