#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_release_face.py -- one version, told the same way on every face.

Why this exists
---------------
tools/verify_release_consistency.py (gate 6) compares the README/INTEGRITY
canonical *pin*, the set digest, the licence lines, the gate count and the
manifest. It never opens .zenodo.json, CITATION.cff, llms.txt or
docs/where-to-find-us.md, and it has no opinion about the GitHub Release or the
Zenodo record.

By 2026-10-09 that blind spot had produced drift that was live and published.
Reading the artifacts instead of the intent (2026-10-09, record-by-record):

  face                            said             while README said
  ------------------------------  ---------------  -----------------
  docs/where-to-find-us.md        0.1.0            v0.1.1
  llms.txt                        0.1.0            v0.1.1
  INTEGRITY.md, Zenodo line       version 0.1.0    v0.1.1
  GitHub Releases                 v0.1.0 only      v0.1.1
  Zenodo, concept 23051637        version 0.1.0    v0.1.1

No gate in the repository could see any of those. Each one is a sentence a
reader is invited to act on: the README names the tag as the canonical citation,
llms.txt told retrieval systems the version was 0.1.0, and Zenodo held an archive
that no release pointed at. The deposit that produced it also carried an
affiliation line (`MedXpert (unregistered name)`) that nobody had re-read since.

What it does
------------
It reads the faces of this release and requires them to agree. The **single
source of truth** for the release version is README.md's canonical-citation
sentence; every other file is a mirror, and this gate is what makes "mirror" a
checkable word instead of a hope (AGENTS.md rule 15).

  in-tree faces -- always run, never skip:

    F1  the release version agrees across all six declaring files
    F2  the concept DOI agrees across README / INTEGRITY / .zenodo.json
    F3  the archived version DOI is well formed, differs from the concept DOI,
        and is the same DOI in README and INTEGRITY
    F4  the archived version *label* is the same in README and INTEGRITY
    F5  the release date agrees across CITATION.cff / llms.txt /
        docs/where-to-find-us.md, and llms.txt is not updated before it
    F6  the four pure-declaration files carry no foreign version token
    F7  every declaring file exists and its claim is extractable (rule 12)

  published faces -- need the network; the strict scope runs on a schedule and
  on every release, see .github/workflows/release-face-remote.yml:

    R1  the declared canonical tag exists
    R2  a GitHub Release exists for it       (absent == FAIL, never a skip)
    R3  the archived DOI is a real Zenodo record carrying the archived version,
        and a record exists for the declared canonical version
    R4  main is protected
    R5  every required status check matches a job name in .github/workflows
        (a required check no job ever reports waits forever -- the dead rule)

The split is deliberate, and it is the difference between a gate that can be
green and a gate that gets ignored. "The tag exists" is a property of a release,
not of a commit under review: enforced at pull-request time it blocks the very
version bump that creates the tag. So the in-tree half runs everywhere, and the
published half runs when a published answer can exist.

Known limits, stated rather than implied
----------------------------------------
  * CHANGELOG.md, REVIEW.md and docs/pull-request-workflow.md are deliberately
    NOT faces. Every line in them is a statement about the release that existed
    on its date; rewriting them would be the same error as moving a tag. A stale
    *narrative* mention in a dated record is therefore not detected here.
  * R5 cannot be evaluated with the default `github.token`: the branch-protection
    API requires admin. In CI it reports NOT VERIFIED, loudly and by name, and
    the limitation is recorded rather than hidden. Run it locally with `gh`
    authenticated as an administrator to close it.
  * F3/F4 record what *was* deposited, so they are allowed to lag the release
    version. The check that a declared release really was deposited is R3, and
    it cannot be made in-tree -- that is why the remote half exists at all.
  * This gate compares declarations to each other and to the published record. It
    cannot tell whether the *content* those declarations describe is right; that
    is what manifest.sha256 and failures/ are for.

Usage
-----
    python tools/verify_release_face.py --repo-path . --no-remote
    python tools/verify_release_face.py --repo-path . --repo owner/name
    python tools/verify_release_face.py --selftest

Exit code: 0 iff no face FAILs. NOT VERIFIED faces are named in the summary and
counted separately -- they are not PASS, and they are not silent.
"""

import argparse
import json
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

VERSION = r"(\d+\.\d+\.\d+)"
DOI = r"(10\.5281/zenodo\.\d+)"
DATE = r"(\d{4}-\d{2}-\d{2})"

# README.md is the single source of truth for the release version. The pattern is
# anchored on the phrase the README actually uses, so a rewrite of that sentence
# is a read failure here (rule 12) rather than a silent pass with nothing read.
RE_TAG = re.compile(r"release tag\s+`v" + VERSION + r"`")
# The archived sentence names the DOI of the *deposited* version and the concept
# DOI. Both are cited by readers, so both are read.
RE_README_ARCH = re.compile(
    r"Archived at Zenodo with DOI \*\*" + DOI + r"\*\* \(version " + VERSION +
    r", " + DATE + r"; concept DOI \*\*" + DOI + r"\*\*\)")
RE_INTEG_ARCH = re.compile(
    r"Archived at Zenodo: DOI \*\*" + DOI + r"\*\* \(concept \*\*" + DOI +
    r"\*\*\), version " + VERSION + r", " + DATE + r"\.")
RE_LLMS_VER = re.compile(r"\(version " + VERSION + r", released " + DATE + r"\)")
RE_LLMS_UPD = re.compile(r"Last updated:\s*" + DATE)
RE_W2FU_VER = re.compile(
    r"\|\s*Version\s*\|\s*" + VERSION + r"\s*·\s*released\s*" + DATE + r"\s*\|")
RE_CFF_VER = re.compile(r"^version:\s*\"?(\d+\.\d+\.\d+)\"?\s*$", re.M)
RE_CFF_DATE = re.compile(r"^date-released:\s*\"?(\d{4}-\d{2}-\d{2})\"?\s*$", re.M)
RE_ANY_VERSION = re.compile(r"\b\d+\.\d+\.\d+\b")

DECLARING = ["README.md", "INTEGRITY.md", ".zenodo.json", "CITATION.cff",
             "llms.txt", "docs/where-to-find-us.md"]
# Files that only ever declare the current release. A version token in one of
# these that is not the release version is drift by construction. README and
# INTEGRITY are excluded on purpose: both carry release history, and a check that
# forbade history would be a check that trains people to delete it.
PURE_DECLARING = ["llms.txt", "docs/where-to-find-us.md", ".zenodo.json",
                  "CITATION.cff"]
# Every allowance is a line pattern plus the reason it is not drift. A bare token
# allowlist would be a blacklist with the same hole as every blacklist.
IGNORED_VERSION_LINES = [
    (re.compile(r"^\s*cff-version:"),
     "the Citation File Format schema version, not this release"),
]
ZENODO_API = "https://zenodo.org/api/records"
# An unauthenticated caller is capped at 25 records per page, so a concept with
# more versions than fit in one page is walked rather than assumed small. 20 pages
# is 500 versions; a software catalogue that reaches that is not this one.
ZENODO_PAGE_LIMIT = 20
# A gateway timeout is evidence about the gateway, not about the concept. On
# 2026-10-10 the scheduled run failed with `R3 ... Zenodo refused the request
# (HTTP 504)` -- a true cause, correctly named, arriving from an upstream that was
# momentarily unreachable. Reported as a finding it is indistinguishable from
# repository drift, and a daily gate that goes red because someone else's
# gateway hiccuped is a gate people learn to ignore. The remedy is the ordinary
# one for a transient transport: retry the *retryable* statuses, bounded, and
# still fail when the retries run out -- so the gate keeps its ability to say no.
ZENODO_ATTEMPTS = 3
ZENODO_RETRY_STATUS = (429, 500, 502, 503, 504)
_RETRY_SLEEP = time.sleep
# A concept has two doors and, until 2026-10-10, this gate only ever knocked on
# one of them. `/api/records?q=conceptrecid:...` is a *search*: it answers with an
# envelope over an index. `/api/records/<conceptrecid>` is a *read*, and it is the
# URL a record's own `links.parent` advertises. Measured on 2026-10-10 against
# concept 10.5281/zenodo.23051637: the read answered HTTP 200 with the concept's
# newest record object, and against an id that is not there it answered
# `404 {"status": 404, "message": "The persistent identifier does not exist."}`.
# That asymmetry is the whole point -- a search that comes back empty is evidence
# about the search, and only a read that 404s is evidence about the concept. On
# 2026-10-10 the search door answered CI with a readable envelope holding nothing
# while the concept read resolved and the version family listed two published
# records, and this gate printed `no record under the concept`: a statement about
# Zenodo's holdings, made from an index that was silent.
ZENODO_CONCEPT_API = ZENODO_API + "/%s"
# The endpoint InvenioRDM documents for "get all versions" (a record's own
# `links.versions` names it). It takes a *recid*, not a concept id -- measured
# 2026-10-10: `/api/records/23051637/versions` is 404 while
# `/api/records/23260442/versions` answers `{"hits": {"total": 2, ...}}` listing
# every version of the family. So the read above is what turns the concept id
# declared in-tree into a recid the version list can be asked about.
ZENODO_VERSIONS_API = ZENODO_API + "/%s/versions"
WORKFLOW_DIR = os.path.join(".github", "workflows")


# --------------------------------------------------------------------------- #
# Reading
# --------------------------------------------------------------------------- #

def read(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except (FileNotFoundError, NotADirectoryError, PermissionError):
        return None
    except UnicodeDecodeError:
        return None


def claim(pattern, text, what, fname, fails, group=1):
    """Exactly one *distinct* value for a pattern, or a recorded failure.

    Zero matches is a failure and not a pass: a claim that cannot be read is a
    claim that does not agree. This is the shape the whole catalog is about --
    an extractor that quietly matches nothing makes every comparison below
    vacuous while printing a green run.
    """
    vals = sorted({m.group(group) for m in pattern.finditer(text)})
    if not vals:
        fails.append("%s: no %s could be read (rule 12 -- an unreadable claim is "
                     "not an agreeing claim)" % (fname, what))
        return None
    if len(vals) > 1:
        fails.append("%s: %d different %s are declared (%s) -- a file that names "
                     "two values does not name one"
                     % (fname, len(vals), what, ", ".join(vals)))
        return None
    return vals[0]


def one_match(pattern, text, what, fname, fails):
    ms = list(pattern.finditer(text))
    if len(ms) != 1:
        fails.append("%s: expected exactly one %s, found %d"
                     % (fname, what, len(ms)))
        return None
    return ms[0]


def zenodo_id(doi):
    """The numeric id Zenodo indexes: `23051637` out of `10.5281/zenodo.23051637`.

    The last path segment of a Zenodo DOI is `zenodo.<id>`, not `<id>` -- so
    `doi.rstrip("/").split("/")[-1]` returns `zenodo.23051637`, and for years the
    gate asked `conceptrecid:zenodo.23051637` and
    `/api/records/zenodo.23051637`. Both are well-formed questions about an id that
    does not exist: the search answers a valid envelope with `hits.total = 0`
    (D-034's "Zenodo holds no record at all"), and the read answers
    `404 The persistent identifier does not exist.` -- which is a true answer to a
    wrong question. The defect survived three fixes because every one of them
    examined the *answer*; none of them ever looked at the *question*. Found on
    2026-10-10 only because D-034 started printing the URL it had asked.
    """
    tail = doi.rstrip("/").split("/")[-1]
    if "." in tail:
        tail = tail.rsplit(".", 1)[-1]
    return tail


# --------------------------------------------------------------------------- #
# In-tree faces
# --------------------------------------------------------------------------- #

def run_static(repo_path, fails):
    """F1..F7. Returns a dict of facts for the remote faces to reuse."""
    facts = {}
    texts = {}
    for name in DECLARING:
        t = read(os.path.join(repo_path, *name.split("/")))
        if t is None:
            # A declaring file that is missing is a failure, not a skip.
            fails.append("%s: missing -- a face that is not there cannot agree "
                         "with anything (rule 12)" % name)
        texts[name] = t

    def t(name):
        return texts.get(name)

    # -- F1: the release version, from every declaring file ----------------
    claims = {}
    if t("README.md") is not None:
        claims["README.md"] = claim(RE_TAG, t("README.md"), "canonical tag",
                                    "README.md", fails)
    zj = None
    if t(".zenodo.json") is not None:
        try:
            zj = json.loads(t(".zenodo.json"))
            v = zj.get("version")
            if not isinstance(v, str) or not re.match(r"^\d+\.\d+\.\d+$", v):
                fails.append(".zenodo.json: version is absent or not X.Y.Z (%r)"
                             % (v,))
                v = None
            claims[".zenodo.json"] = v
        except ValueError as e:
            fails.append(".zenodo.json: not parseable as JSON (%s)" % e)
    if t("CITATION.cff") is not None:
        claims["CITATION.cff"] = claim(RE_CFF_VER, t("CITATION.cff"),
                                       "version", "CITATION.cff", fails)
    for name in ("llms.txt", "docs/where-to-find-us.md"):
        if t(name) is not None:
            pat = RE_LLMS_VER if name == "llms.txt" else RE_W2FU_VER
            claims[name] = claim(pat, t(name), "version",
                                 name, fails)

    # INTEGRITY declares the canonical pin in the same sentence form as README.
    if t("INTEGRITY.md") is not None:
        # The tag claim is read on its own pattern, not as a by-product of the
        # archive sentence: a reworded archive line must fail the archive check
        # only, and must not take the tag claim down with it.
        facts["_integ_arch"] = one_match(
            RE_INTEG_ARCH, t("INTEGRITY.md"), "Zenodo archive line",
            "INTEGRITY.md", fails)
        claims["INTEGRITY.md"] = claim(RE_TAG, t("INTEGRITY.md"),
                                       "canonical tag", "INTEGRITY.md", fails)

    known = {k: v for k, v in claims.items() if v}
    if len(known) != len(DECLARING):
        fails.append("F1: only %d of %d declaring files yielded a release version"
                     % (len(known), len(DECLARING)))
    if len(set(known.values())) > 1:
        fails.append("F1: the release version disagrees across the faces: %s"
                     % "; ".join("%s=%s" % kv for kv in sorted(known.items())))
    release = None
    if len(set(known.values())) == 1 and len(known) == len(DECLARING):
        release = list(known.values())[0]
    facts["release"] = release
    facts["_claims"] = known

    # -- F2/F3/F4: the DOIs and the archived label -------------------------
    readme_arch = integ_arch = None
    if t("README.md") is not None:
        readme_arch = one_match(RE_README_ARCH, t("README.md"),
                                "Zenodo archive sentence", "README.md", fails)
    integ_arch = facts.get("_integ_arch")

    concept = {}
    if readme_arch is not None:
        concept["README.md"] = readme_arch.group(4)
    if integ_arch is not None:
        concept["INTEGRITY.md"] = integ_arch.group(2)
    if zj is not None:
        ris = [r for r in zj.get("related_identifiers", [])
               if r.get("relation") == "isPartOf"]
        if len(ris) != 1:
            fails.append(".zenodo.json: expected exactly one isPartOf relation, "
                         "found %d" % len(ris))
        else:
            ident = ris[0].get("identifier", "")
            m = re.search(DOI, ident)
            if not m:
                fails.append(".zenodo.json: isPartOf identifier is not a Zenodo "
                             "DOI (%r)" % ident)
            else:
                concept[".zenodo.json"] = m.group(1)
    if len(concept) != 3:
        fails.append("F2: the concept DOI could be read from only %d of 3 files"
                     % len(concept))
    if len(set(concept.values())) > 1:
        fails.append("F2: the concept DOI disagrees: %s"
                     % "; ".join("%s=%s" % kv for kv in sorted(concept.items())))
    facts["concept"] = list(set(concept.values()))[0] if concept else None

    ver_doi = {}
    if readme_arch is not None:
        ver_doi["README.md"] = readme_arch.group(1)
    if integ_arch is not None:
        ver_doi["INTEGRITY.md"] = integ_arch.group(1)
    if len(ver_doi) != 2:
        fails.append("F3: the archived version DOI could be read from only %d of "
                     "2 files" % len(ver_doi))
    else:
        vals = set(ver_doi.values())
        if len(vals) > 1:
            fails.append("F3: the archived version DOI disagrees: %s"
                         % "; ".join("%s=%s" % kv for kv in sorted(ver_doi.items())))
        doi = list(vals)[0]
        if facts["concept"] and zenodo_id(doi) == zenodo_id(facts["concept"]):
            fails.append("F3: the archived version DOI is the concept DOI (%s) -- "
                         "the two identifiers are not interchangeable" % doi)
    facts["archived_doi"] = list(set(ver_doi.values()))[0] if ver_doi else None
    facts["_ver_doi"] = ver_doi

    ver_label = {}
    if readme_arch is not None:
        ver_label["README.md"] = readme_arch.group(2)
    if integ_arch is not None:
        ver_label["INTEGRITY.md"] = integ_arch.group(3)
    if len(ver_label) != 2:
        fails.append("F4: the archived version label could be read from only %d "
                     "of 2 files" % len(ver_label))
    elif len(set(ver_label.values())) > 1:
        fails.append("F4: the archived version label disagrees: %s"
                     % "; ".join("%s=%s" % kv for kv in sorted(ver_label.items())))
    facts["archived_version"] = (list(set(ver_label.values()))[0]
                                 if ver_label else None)
    facts["_ver_label"] = ver_label

    # -- F5: the release date ----------------------------------------------
    dates = {}
    if t("CITATION.cff") is not None:
        dates["CITATION.cff"] = claim(RE_CFF_DATE, t("CITATION.cff"),
                                      "date-released", "CITATION.cff", fails)
    if t("llms.txt") is not None:
        dates["llms.txt"] = claim(RE_LLMS_VER, t("llms.txt"), "release date",
                                  "llms.txt", fails, group=2)
    if t("docs/where-to-find-us.md") is not None:
        dates["docs/where-to-find-us.md"] = claim(
            RE_W2FU_VER, t("docs/where-to-find-us.md"), "release date",
            "docs/where-to-find-us.md", fails, group=2)
    if len(dates) != 3:
        fails.append("F5: the release date could be read from only %d of 3 files"
                     % len(dates))
    elif len(set(dates.values())) > 1:
        fails.append("F5: the release date disagrees: %s"
                     % "; ".join("%s=%s" % kv for kv in sorted(dates.items())))
    if t("llms.txt") is not None and dates.get("llms.txt"):
        upd = claim(RE_LLMS_UPD, t("llms.txt"), "\"Last updated\" date",
                    "llms.txt", fails)
        if upd and upd < dates["llms.txt"]:
            fails.append("F5: llms.txt says it was last updated %s, before the "
                         "release it announces (%s)" % (upd, dates["llms.txt"]))
    facts["_dates"] = dates

    # -- F6: no foreign version token in the pure-declaration files --------
    if release is None:
        # One reported failure, not one per token: without a single release
        # version there is nothing to compare against, and a page of cascaded
        # findings buries the two lines above that actually explain it.
        fails.append("F6: not evaluated -- no single release version could be "
                     "read, so no token can be called foreign")
    else:
        for name in PURE_DECLARING:
            text = t(name)
            if text is None:
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                if any(p.search(line) for p, _why in IGNORED_VERSION_LINES):
                    continue
                for tok in RE_ANY_VERSION.findall(line):
                    if tok == release:
                        continue
                    fails.append(
                        "F6: %s:%d carries a version token (%s) that is not the "
                        "release version (%s) -- a pure declaration file has no "
                        "release history to preserve"
                        % (name, lineno, tok, release))
    return facts


# --------------------------------------------------------------------------- #
# Published faces
# --------------------------------------------------------------------------- #

class RealAPI(object):
    def __init__(self, repo):
        self.repo = repo

    def _gh(self, path):
        try:
            p = subprocess.run(["gh", "api", path], capture_output=True,
                               text=True, timeout=60)
        except (OSError, subprocess.SubprocessError) as e:
            return (None, "gh could not be run: %s" % e)
        if p.returncode != 0:
            return (False, (p.stderr or p.stdout).strip().splitlines()[:1])
        try:
            return (True, json.loads(p.stdout))
        except ValueError as e:
            return (None, "gh returned non-JSON: %s" % e)

    def tag_exists(self, tag):
        ok, payload = self._gh("repos/%s/git/refs/tags/%s" % (self.repo, tag))
        if ok is None:
            return (None, payload)
        if ok:
            return (True, "ref resolves")
        return (False, "no ref refs/tags/%s (%s)" % (tag, payload))

    def release_exists(self, tag):
        ok, payload = self._gh("repos/%s/releases/tags/%s" % (self.repo, tag))
        if ok is None:
            return (None, payload)
        if ok:
            return (True, "release %s published=%s"
                    % (payload.get("tag_name"), payload.get("published_at")))
        return (False, "no GitHub Release for %s (%s)" % (tag, payload))

    def branch_protected(self):
        ok, payload = self._gh("repos/%s/branches/main" % self.repo)
        if ok is None:
            return (None, payload)
        if not ok:
            return (False, "main not readable (%s)" % (payload,))
        return (bool(payload.get("protected")),
                "protected=%s" % payload.get("protected"))

    def required_checks(self):
        ok, payload = self._gh("repos/%s/branches/main/protection" % self.repo)
        if ok is None:
            return (None, payload)
        if not ok:
            return (None, "branch-protection API refused this token (%s) -- this "
                          "is the default `github.token`, which has no admin "
                          "access; run locally with an administrator's gh to "
                          "close it" % (payload,))
        ctxs = (payload.get("required_status_checks") or {}).get("contexts") or []
        return (list(ctxs), "%d required check(s)" % len(ctxs))

    def _open(self, req, timeout=90):
        """The single place this class touches the network.

        Split out so the selftest can drive the *transport* failure paths
        (a rejection, a paginated concept) without monkey-patching urllib for
        every other test in the file.
        """
        return urllib.request.urlopen(req, timeout=timeout)

    def _sleep(self, seconds):
        """Split out like `_open`, so a case can drive retry timing without waiting."""
        _RETRY_SLEEP(seconds)

    def _zenodo_get(self, url):
        """One bounded attempt loop over one GET.

        Returns ``(body, status, error)``; ``error`` is a dict carrying ``status``
        (the HTTP code, when there was one) and ``why`` (the sentence a finding
        should repeat). Both doors share this one retry policy rather than keeping
        two copies of it, and both are reachable from a case, so a retry can be
        driven without waiting on it.

        A gateway timeout is a statement about the gateway. Retrying it is the
        ordinary remedy, and the retry is bounded so it can never become an
        exemption: when the attempts run out the finding stands and says how many
        were made. Only statuses that mean "try again later" are retried; a 4xx is
        the answer, not a hiccup, and is reported on the first reply.
        """
        req = urllib.request.Request(url, headers={
            "Accept": "application/json", "User-Agent": "verify_release_face"})
        for attempt in range(1, ZENODO_ATTEMPTS + 1):
            try:
                with self._open(req) as resp:
                    body = resp.read().decode("utf-8", "replace")
                    status = getattr(resp, "status", None)
                return (body, status, None)
            except urllib.error.HTTPError as e:
                try:
                    detail = e.read().decode("utf-8", "replace").strip()[:300]
                except Exception:                    # noqa: BLE001
                    detail = ""
                if e.code in ZENODO_RETRY_STATUS and attempt < ZENODO_ATTEMPTS:
                    self._sleep(attempt)             # 1s, 2s -- bounded, no jitter
                    continue
                after = "" if attempt == 1 else " after %d attempts" % attempt
                return (None, e.code, {
                    "status": e.code, "body": detail,
                    "why": "Zenodo refused the request (HTTP %s)%s: %s"
                           % (e.code, after, detail or "(no body)")})
            except Exception as e:  # noqa: BLE001 - other transport failure is the message
                if attempt < ZENODO_ATTEMPTS:
                    self._sleep(attempt)
                    continue
                return (None, None, {
                    "status": None, "body": "",
                    "why": "Zenodo API unreachable from here (%s)" % e})
        return (None, None, {
            "status": None, "body": "",
            "why": "Zenodo gave no answer after %d attempts" % ZENODO_ATTEMPTS})

    @staticmethod
    def _records_envelope(data, what):
        """The `hits` object of a search-style envelope, or a refusal to read it.

        A 200 whose body is not the envelope is not an empty result. On 2026-10-09
        the remote run printed `R3 FAIL no record under the concept` for a concept
        Zenodo's own API lists two published records under: the body had parsed,
        but `((data or {}).get("hits") or {}).get("hits") or []` quietly made
        "field absent" read as "records absent". Requiring the envelope -- and
        reporting the keys that did arrive -- separates "nothing is there" from
        "this page cannot be read", which are two different findings and must not
        share one sentence.
        """
        hits_obj = (data or {}).get("hits")
        if not isinstance(hits_obj, dict) or "total" not in hits_obj:
            keys = ", ".join(sorted((data or {}).keys()))[:160] or "(none)"
            return (None, "%s answered HTTP 200 but not with a records envelope "
                          "(top-level keys: %s) -- an unreadable page is not an "
                          "empty result" % (what, keys))
        return (hits_obj, None)

    def _walk_envelope(self, url, what):
        """Walk a search-style envelope to its last page.

        Returns ``(records, note, error)``. The note is returned even on success,
        because it is also the evidence a passing run should not have to re-fetch.
        The walk follows the API's own `links.next` rather than synthesising
        `page=2`, so it follows the index's own ordering, and an unauthenticated
        caller is never assumed to fit in one page: asking for `size=100` is not a
        larger request, it is a rejected one -- Zenodo answers 400, "Page size
        cannot be greater than 25. Please use authenticated requests to increase
        the limit to 100" -- which a blanket `except` once reported as
        unreachability.
        """
        out, pages, status, total = [], 0, None, None
        for _ in range(ZENODO_PAGE_LIMIT):
            body, status, err = self._zenodo_get(url)
            if err is not None:
                return (None, None, err["why"])
            pages += 1
            try:
                data = json.loads(body)
            except ValueError as e:
                return (None, None, "Zenodo returned non-JSON (%s)" % e)
            hits_obj, unreadable = self._records_envelope(data, what)
            if unreadable is not None:
                return (None, None, unreadable)
            total = hits_obj.get("total")
            for hit in hits_obj.get("hits") or []:
                md = hit.get("metadata") or {}
                out.append({
                    "doi": hit.get("doi"),
                    "version": md.get("version"),
                    "published": bool(hit.get("submitted")),
                    "created": hit.get("created") or "",
                })
            nxt = ((data or {}).get("links") or {}).get("next") or ""
            if not nxt:
                break
            url = nxt
        note = "HTTP %s, hits.total=%s, %d record(s) in %d page(s)" % (
            status, total, len(out), pages)
        return (out, note, None)

    @staticmethod
    def _concept_absence(url, body):
        """``(result, why)`` for a 404 at the concept door.

        A 404 is evidence that the concept is absent only when Vol. 2 -- Zenodo
        itself -- is the one speaking. Measured 2026-10-10 on an id that is not
        there: `404 {"status": 404, "message": "The persistent identifier does not
        exist."}`. A 404 that is *not* that -- an HTML block page from something
        sitting in front of Zenodo, say -- is an answer this probe cannot read, and
        reading it as absence would repeat the same error one layer down: a page
        that cannot be parsed, recorded as a fact about the world. So the body has
        to name a missing identifier in Zenodo's own error envelope, and when it
        does not, both the body and the refusal are printed.
        """
        try:
            data = json.loads(body or "")
        except ValueError:
            data = None
        if isinstance(data, dict) and data.get("status") == 404:
            return (False, "the concept read answered HTTP 404 at %s: %s"
                           % (url, data.get("message") or "(no message)"))
        return (None, "the concept read answered HTTP 404 at %s but not with "
                      "Zenodo's own error body (%s) -- an answer this probe cannot "
                      "read is not evidence that the concept is absent"
                      % (url, (body or "(no body)").strip()[:200]))

    def zenodo_concept(self, concept_doi):
        """Read the concept itself -- the door that is not a search.

        ``(True, info)`` when the concept resolves, ``(False, why)`` when Zenodo
        says the identifier does not exist, ``(None, why)`` when the answer cannot
        be read at all. Only the middle case is evidence about the concept; the
        third is evidence about this probe, and the caller must not let the two
        share a sentence.
        """
        url = ZENODO_CONCEPT_API % zenodo_id(concept_doi)
        body, status, err = self._zenodo_get(url)
        if err is not None:
            if err.get("status") == 404:
                return self._concept_absence(url, err.get("body"))
            return (None, err["why"])
        if status == 404:
            return self._concept_absence(url, body)
        try:
            data = json.loads(body)
        except ValueError as e:
            return (None, "the concept read returned non-JSON (%s)" % e)
        if not isinstance(data, dict) or "conceptrecid" not in data:
            keys = ", ".join(sorted((data or {}).keys()))[:160] or "(none)"
            return (None, "the concept read answered HTTP %s but not with a record "
                          "object (top-level keys: %s)" % (status, keys))
        return (True, {
            "recid": str(data.get("id") or data.get("recid") or ""),
            "doi": data.get("doi"),
            "version": (data.get("metadata") or {}).get("version"),
            "versions_url": (data.get("links") or {}).get("versions") or "",
            "url": url,
        })

    def zenodo_records(self, concept_doi):
        """Every version under the concept -- read, not searched.

        `recs` is `None` when the answer could not be read (a finding about this
        probe), `[]` when the read resolved and the family really is empty (a
        finding about the concept), and the records otherwise. The two have to
        stay apart: the 2026-10-10 defect was exactly one being read as the other.
        """
        state, info = self.zenodo_concept(concept_doi)
        if state is False:
            return ([], info)
        if state is None:
            return (None, info)
        url = info["versions_url"] or (ZENODO_VERSIONS_API % info["recid"])
        recs, note, err = self._walk_envelope(url, "the versions endpoint")
        if err is not None:
            return (None, err)
        if not recs:
            return ([], "concept %s resolved (%s) and its version family came back "
                        "empty -- %s, url %s"
                        % (concept_doi, info["url"], note, url))
        return (recs, "%d record(s) read from the concept's own version family "
                      "(%s)" % (len(recs), note))

    def zenodo_search(self, concept_doi):
        """What the *search* index says -- kept only to be reported beside the read.

        Never allowed to decide the verdict. On 2026-10-10 this is the door that
        came back empty from CI while the concept read resolved and the version
        family held two published records. A disagreement between two of Zenodo's
        own doors is worth recording on every run -- it is the evidence that
        closes that question -- but it is not repository drift, and a gate that
        let it decide would be back where it started.
        """
        url = "%s?q=conceptrecid:%s&allversions=true&size=25" % (
            ZENODO_API, zenodo_id(concept_doi))
        recs, note, err = self._walk_envelope(url, "the search endpoint")
        if err is not None:
            return (None, err)
        return (len(recs), note)


def workflow_job_name_patterns(repo_path):
    """Every job name declared in .github/workflows, as a regex.

    Matrix expressions (``gates · python ${{ matrix.python }}``) are turned into
    a wildcard, because the required-check context is the *expanded* name the
    runner reports (`gates · python 3.9`). Matching the unexpanded string would
    report a live rule as dead -- a false alarm in the direction that trains
    people to ignore alarms.

    Only the map under ``jobs:`` is read. A one-indent key anywhere in the file
    is not a job: ``on:`` has children too (``push:``, ``pull_request:``), and a
    scanner that accepted them would answer "that required check is reported by
    a job" for a context named ``push`` -- a false PASS in the direction this
    gate exists to prevent. Measured, not assumed: the first revision of this
    function did exactly that, and case R5-on-key-not-a-job is what found it.
    """
    pats = []
    wf_dir = os.path.join(repo_path, WORKFLOW_DIR)
    if not os.path.isdir(wf_dir):
        return pats
    for fn in sorted(os.listdir(wf_dir)):
        if not fn.endswith((".yml", ".yaml")):
            continue
        text = read(os.path.join(wf_dir, fn)) or ""
        m = re.search(r"^jobs:\s*$", text, re.M)
        if m is None:
            continue
        tail = text[m.end():]
        stop = re.search(r"^\S", tail, re.M)
        body = tail[:stop.start()] if stop else tail
        starts = [mm.start() for mm in re.finditer(r"^  ([A-Za-z0-9_-]+):\s*$",
                                                   body, re.M)]
        bounds = starts + [len(body)]
        for i, off in enumerate(starts):
            block = body[off:bounds[i + 1]]
            jid = re.match(r"^  ([A-Za-z0-9_-]+):", block).group(1)
            nm = re.search(r"^    name:\s*(.+?)\s*$", block, re.M)
            name = nm.group(1).strip().strip('"').strip("'") if nm else jid
            pats.append((name, _name_to_regex(name), "%s:%s" % (fn, jid)))
    return pats


def _name_to_regex(name):
    ph = "\x00M\x00"
    tmp = re.sub(r"\$\{\{[^}]*\}\}", ph, name)
    return "^" + re.escape(tmp).replace(re.escape(ph), ".+?") + "$"


def run_remote(repo_path, repo, api, facts, fails, not_verified, zenodo=True,
               notes=None):
    notes = [] if notes is None else notes
    table = []
    tag = "v" + facts["release"] if facts.get("release") else None

    if tag is None:
        fails.append("R1: the release version could not be read in-tree, so no "
                     "published face can be checked (the in-tree failure above "
                     "is the cause)")
        return table

    def face(rid, what, result):
        """A published face: True passes, False fails, None cannot be run.

        ``None`` is a failure and never a skip. The one face that is allowed to
        report NOT VERIFIED is R5, and it is handled separately below with its
        reason attached -- a rule that cannot be read is different from a probe
        that did not run.
        """
        ok, msg = result
        if ok is None:
            fails.append("%s %s: %s (rule 12 -- cannot verify is not verified)"
                         % (rid, what, msg))
            table.append((rid, what, "FAIL", msg))
        elif not ok:
            fails.append("%s: %s" % (rid, msg))
            table.append((rid, what, "FAIL", msg))
        else:
            # A face that passed is printed too. A table that only ever shows
            # failures cannot tell "walked and found nothing" from "never walked",
            # which is the whole subject of this repository.
            table.append((rid, what, "PASS", msg))

    face("R1", "tag " + tag, api.tag_exists(tag))
    face("R2", "Release " + tag, api.release_exists(tag))
    face("R4", "main protected", api.branch_protected())

    required, why = api.required_checks()
    if required is None:
        not_verified.append("R5 required checks: %s" % why)
        table.append(("R5", "required status checks", "NOT VERIFIED", why))
    else:
        # The verdict is derived from the findings, never asserted alongside them:
        # a table row that says PASS while the same branch appended a failure is
        # the "summary says green, verdict says red" defect recorded as D-023.
        r5_before = len(fails)
        pats = workflow_job_name_patterns(repo_path)
        if not pats:
            fails.append("R5: no job names could be read from %s -- cannot tell "
                         "whether the required checks are reported by anything"
                         % WORKFLOW_DIR)
        else:
            names = {p[0] for p in pats}
            unmatched = [c for c in required
                         if not any(re.match(rx, c) for _n, rx, _w in pats)]
            if unmatched:
                fails.append(
                    "R5: %d required status check(s) match no job in %s and will "
                    "wait forever: %s"
                    % (len(unmatched), WORKFLOW_DIR, unmatched))
            jobs_not_required = sorted(names - set(required))
            if jobs_not_required:
                notes.append(
                    "%d job(s) exist but are not required checks (%s). Adding a "
                    "job to the required list before it has reported once creates "
                    "the same dead rule, so the order is: let it run, then "
                    "require it."
                    % (len(jobs_not_required), ", ".join(jobs_not_required)))
        table.append(("R5", "required status checks",
                      "FAIL" if len(fails) > r5_before else "PASS", why))

    if not zenodo:
        not_verified.append("R3 Zenodo record: skipped by --no-zenodo")
        table.append(("R3", "Zenodo record for " + facts["release"], "NOT VERIFIED",
                      "skipped by --no-zenodo"))
        return table
    if not facts.get("concept"):
        fails.append("R3: the concept DOI could not be read in-tree, so the "
                     "Zenodo side cannot be checked")
        table.append(("R3", "Zenodo record", "FAIL", "concept DOI unreadable"))
        return table
    recs, msg = api.zenodo_records(facts["concept"])
    if recs is None:
        fails.append("R3: %s -- cannot verify is not verified (rule 12)" % msg)
        table.append(("R3", "Zenodo record", "FAIL", msg))
        return table
    # The other door is recorded on every run, and it is not asked to decide
    # anything. `zenodo_records` read the concept; this reports what the *search*
    # index said about the same concept, so a run where the two disagree leaves
    # evidence instead of a puzzle. On 2026-10-10 the search door answered CI with
    # a readable envelope holding nothing while the concept read resolved and
    # /api/records/23260442/versions listed two published records -- and the gate
    # believed the search.
    searched, search_note = api.zenodo_search(facts["concept"])
    notes.append("R3 cross-door: read=%s; search=%s"
                 % (msg, search_note if searched is None
                    else "%d record(s) -- %s" % (searched, search_note)))
    if not recs:
        fails.append("R3: Zenodo holds no record at all under concept %s -- %s"
                     % (facts["concept"], msg))
        table.append(("R3", "Zenodo record", "FAIL", "no record under the concept"))
        return table
    by_doi = {r["doi"]: r for r in recs if r.get("doi")}
    arch = facts.get("archived_doi")
    if arch not in by_doi:
        fails.append("R3: the archived DOI cited in-tree (%s) is not one of the "
                     "records under concept %s (%s)"
                     % (arch, facts["concept"], sorted(by_doi)))
    else:
        got = by_doi[arch].get("version")
        if got != facts.get("archived_version"):
            fails.append("R3: the in-tree archive line says version %s for DOI "
                         "%s, but the record says %s"
                         % (facts.get("archived_version"), arch, got))
        # That check only proves the sentence does not lie about the record it
        # names. It says nothing about *which* record it names, and an archive line
        # that still points at the previous version passes it. On 2026-10-09 the
        # README sent readers to the 0.1.0 DOI while 0.1.2 sat published beside it
        # under the same concept, and this gate was green -- because "a record
        # carrying the release version exists" and "the repository points at it"
        # are two different claims, and only the first was checked. The repository's
        # own sentence settles the intent: "the newest archived version is the 0.1.0
        # record; INTEGRITY.md is updated in the same move as the DOI". So when a
        # record carrying the release version exists, the archive line must be it.
        newest = [r for r in recs
                  if r.get("version") == facts["release"] and r.get("published")]
        if newest and got != facts["release"]:
            fails.append(
                "R3: the archive line names DOI %s (version %s) while concept %s "
                "already holds a record carrying the release version %s (%s) -- "
                "readers are being sent to a superseded archive"
                % (arch, got, facts["concept"], facts["release"],
                   ", ".join(sorted(r["doi"] for r in newest if r.get("doi")))))
    declared = [r for r in recs if r.get("version") == facts["release"]
                and r.get("published")]
    if not declared:
        fails.append(
            "R3: the release version %s is declared as the canonical citation but "
            "no Zenodo record under concept %s carries it (records: %s) -- a "
            "declared release that was never deposited"
            % (facts["release"], facts["concept"],
               sorted({(r.get("version"), r.get("published")) for r in recs})))
    # Verdict for R3 is derived from the two failure lists, not asserted: a face
    # that says PASS has to mean the checks above added nothing.
    before = len(not_verified)
    r3_ok = not any(f.startswith("R3") for f in fails) and \
        len(not_verified) == before
    table.append(("R3", "Zenodo record for " + facts["release"],
                  "PASS" if r3_ok else "FAIL",
                  "%d record(s) under the concept" % len(recs)))
    return table


# --------------------------------------------------------------------------- #
# Selftest -- a throw-away repository per case
# --------------------------------------------------------------------------- #

GOOD = {
    "README.md": (
        "# Synthetic\n\n"
        "**Canonical citation: the immutable release tag `v9.9.9`** -- and `v9.9.8` "
        "is superseded.\n\n"
        "Archived at Zenodo with DOI **10.5281/zenodo.11111112** (version 9.9.9, "
        "2026-01-03; concept DOI **10.5281/zenodo.11111110**).\n"),
    "INTEGRITY.md": (
        "# Synthetic integrity\n\n"
        "- Archived at Zenodo: DOI **10.5281/zenodo.11111112** (concept "
        "**10.5281/zenodo.11111110**), version 9.9.9, 2026-01-03.\n"
        "- Canonical pin for citations: **immutable release tag `v9.9.9`** (see "
        "README).\n"),
    ".zenodo.json": json.dumps({
        "title": "Synthetic",
        "version": "9.9.9",
        "related_identifiers": [
            {"identifier": "https://doi.org/10.5281/zenodo.11111110",
             "relation": "isPartOf", "scheme": "doi"},
        ],
    }, indent=2) + "\n",
    "CITATION.cff": (
        "cff-version: 1.2.0\nmessage: \"cite\"\ntitle: \"Synthetic\"\n"
        "version: \"9.9.9\"\ndate-released: \"2026-01-02\"\n"),
    "llms.txt": (
        "# Synthetic\n\nLast updated: 2026-01-02.\n\n"
        "- **Canonical URL**: https://example.invalid (version 9.9.9, released "
        "2026-01-02)\n"),
    "docs/where-to-find-us.md": (
        "# Synthetic\n\n| Version | 9.9.9 · released 2026-01-02 |\n"),
    os.path.join(WORKFLOW_DIR, "gates.yml"): (
        "name: gates\n"
        "on:\n  push:\njobs:\n"
        "  gates:\n"
        "    name: gates · python ${{ matrix.python }}\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n      - name: run\n        run: echo hi\n"
        "  negative-control:\n"
        "    name: negative control · the manifest gate must be able to fail\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n      - name: x\n        run: echo\n"
        "  release-face:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n      - name: y\n        run: echo\n"),
}


class FakeAPI(object):
    """A stand-in for the published faces, with a canary.

    ``calls`` is the canary. If a case expects the fake to have been used and it
    was not, the code reached the real network instead -- a green run built on
    live data, which is the failure this whole file is about. Confirmed the hard
    way on 2026-10-09: the deposit rehearsal replaced ``sys.modules`` only, and
    `import urllib.request` bound the *package attribute*, so the block went to
    zenodo.org while the harness reported success.
    """

    def __init__(self, tag=True, release=True, protected=True,
                 contexts=None, records=None, gh_broken=False,
                 deny_protection=False):
        self.tag = tag
        self.release = release
        self.protected = protected
        self.contexts = contexts if contexts is not None else [
            "gates · python 3.9",
            "negative control · the manifest gate must be able to fail"]
        self.records = records if records is not None else [
            {"doi": "10.5281/zenodo.11111111", "version": "9.9.8",
             "published": True, "created": "2026-01-02T00:00:00Z"},
            {"doi": "10.5281/zenodo.11111112", "version": "9.9.9",
             "published": True, "created": "2026-01-03T00:00:00Z"},
        ]
        self.gh_broken = gh_broken
        self.deny_protection = deny_protection
        self.calls = {"gh": 0, "zen": 0}

    def tag_exists(self, tag):
        self.calls["gh"] += 1
        if self.gh_broken:
            return (None, "gh could not be run")
        return (self.tag, "ref resolves" if self.tag else "no ref " + tag)

    def release_exists(self, tag):
        self.calls["gh"] += 1
        if self.gh_broken:
            return (None, "gh could not be run")
        return (self.release, "a release" if self.release
                else "no GitHub Release for " + tag)

    def branch_protected(self):
        self.calls["gh"] += 1
        if self.gh_broken:
            return (None, "gh could not be run")
        return (self.protected, "protected=%s" % self.protected)

    def required_checks(self):
        self.calls["gh"] += 1
        if self.deny_protection:
            return (None, "the branch-protection API refused this token (403)")
        return (self.contexts, "%d required" % len(self.contexts))

    def zenodo_records(self, concept_doi):
        self.calls["zen"] += 1
        return (self.records, "%d record(s)" % len(self.records))

    def zenodo_search(self, concept_doi):
        self.calls["zen"] += 1
        return (len(self.records), "HTTP 200, hits.total=%d" % len(self.records))


def _build(root, overrides=None, drop=None):
    files = dict(GOOD)
    if overrides:
        for k, v in overrides.items():
            if v is None:
                files.pop(k, None)
            else:
                files[k] = v
    if drop:
        for k in drop:
            files.pop(k, None)
    for rel, body in files.items():
        path = os.path.join(root, *rel.split("/"))
        d = os.path.dirname(path)
        if d and not os.path.isdir(d):
            os.makedirs(d)
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(body)


class _FakeResp(object):
    def __init__(self, body, status=200):
        self._b = io.BytesIO(body.encode("utf-8") if isinstance(body, str) else body)
        self.status = status

    def read(self):
        return self._b.read()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _TransportAPI(RealAPI):
    """RealAPI with only its network edge replaced.

    The Zenodo face of RealAPI never touches the repository, so the transport
    paths -- a rejection, a paginated concept -- can be driven through the real
    implementation instead of through a stub that returns a canned tuple. That
    distinction is the point: a stub that returns `(records, "%d record(s)")`
    cannot express "the API refused this request", which is how the wrong-cause
    defect of 2026-10-09 stayed invisible to 25 passing cases.
    """

    def __init__(self, pages=None, reject=None, outcomes=None, repo="owner/name"):
        super(_TransportAPI, self).__init__(repo)
        self.pages = list(pages or [])
        self.reject = reject
        # An ordered script of answers, each either a refusal or a page, so a case
        # can say "the gateway timed out, then it answered" -- which `reject` (always
        # refuse) and `pages` (always answer) cannot express between them.
        self.outcomes = list(outcomes or [])
        self.sleeps = []
        self.urls = []
        self.calls = {"zen": 0}
        # Inheriting RealAPI also inherits its `gh` half, which shells out to the
        # real GitHub. These cases are about the Zenodo transport, so that half is
        # stubbed: otherwise the case runs a live `gh api` against a repository
        # that does not exist and hangs until the runner kills it.
        self._gh_stub = FakeAPI()

    def tag_exists(self, tag):
        return self._gh_stub.tag_exists(tag)

    def release_exists(self, tag):
        return self._gh_stub.release_exists(tag)

    def branch_protected(self):
        return self._gh_stub.branch_protected()

    def required_checks(self):
        return self._gh_stub.required_checks()

    def _sleep(self, seconds):
        # Retry timing is the code under test, not something a case should wait on.
        self.sleeps.append(seconds)

    def _open(self, req, timeout=90):
        self.calls["zen"] += 1
        # The URL is recorded, because a case has to be able to pin the *question*
        # and not only the answer. For years this gate asked
        # `conceptrecid:zenodo.23051637` and every one of its 36 cases passed: the
        # fake transport answers whatever it is handed, so a well-formed question
        # about a nonexistent id was indistinguishable from the right one.
        self.urls.append(getattr(req, "full_url", "") or "")
        if self.outcomes:
            step = self.outcomes.pop(0)
            if step[0] == "reject":
                _, code, body = step
                raise urllib.error.HTTPError(req.full_url, code, "refused", {},
                                             io.BytesIO(body.encode("utf-8")))
            _, body, status = step
            return _FakeResp(body, status)
        if self.reject is not None:
            code, body = self.reject
            raise urllib.error.HTTPError(req.full_url, code, "refused", {},
                                         io.BytesIO(body.encode("utf-8")))
        if not self.pages:
            raise AssertionError("the case asked for more pages than it supplied")
        body, status = self.pages.pop(0)
        return _FakeResp(body, status)


def selftest():
    cases = []

    def _all_in(want, text):
        """`want_fail_text` may be one string or several; several must all appear.

        A finding has to carry both its claim and the evidence for it, and pinning
        only the claim is how "a failure for the wrong reason" stays invisible
        (SF-012). A 404 that says "no record under the concept" proves the gate can
        still say no; only the 404 in the same sentence proves it is saying it for
        the right reason.
        """
        if isinstance(want, (list, tuple)):
            return all(w in text for w in want)
        return want in text

    def run_case(cid, what, override=None, drop=None, api=None, zenodo=True,
                 want_fail=True, expect_api_calls=None, want_nv=0,
                 want_harness_error=False, want_fail_text=None,
                 forbid_fail_text=None, want_urls=None):
        root = tempfile.mkdtemp(prefix="face-%s-" % cid)
        harness = []
        a = None
        try:
            _build(root, override, drop)
            fails, nv = [], []
            facts = run_static(root, fails)
            if api is not None or expect_api_calls:
                a = api if api is not None else FakeAPI()
                # The published half is only meaningful once the in-tree half is
                # clean. When it is not, the stub is never called -- and a case
                # must not be credited on the strength of a stub it never used.
                # That is a harness defect, kept in its own channel so it can be
                # asserted on directly (see CANARY-unskippable below) rather than
                # folded into the failure the case was already expecting.
                exercised = not fails
                if exercised:
                    run_remote(root, "owner/name", a, facts, fails, nv, zenodo,
                               notes=[])
                if expect_api_calls is not None:
                    if not exercised:
                        harness.append(
                            "the published faces were never exercised (the "
                            "in-tree faces failed first), so the stub was not "
                            "called")
                    else:
                        for k, want in expect_api_calls.items():
                            got = a.calls[k]
                            if got < want:
                                harness.append(
                                    "the fake API was called %d time(s) for %r, "
                                    "expected >= %d -- the code reached the "
                                    "real network instead of the stub"
                                    % (got, k, want))
        finally:
            shutil.rmtree(root, ignore_errors=True)
        got_fail = bool(fails)
        # A case may also pin the *reason*, not only the failure. Right failure /
        # wrong cause is its own defect (SF-012), and it is the one a
        # `want_fail=True` cannot see: the 2026-10-09 probe failed for a rejected
        # `size=100` and said "unreachable", which reads as a network problem.
        text = "\n".join(fails)
        # A case may also pin the *question*, not only the answer. Every gate here
        # asks something over the network, and a fake transport answers whatever it
        # is handed -- so 36 cases passed while the gate asked
        # `conceptrecid:zenodo.23051637`. Pinning the URL is the only way a case can
        # see the difference between a well-formed question about the wrong id and
        # the right one.
        url_ok, url_detail = True, ""
        if want_urls is not None:
            asked = getattr(a, "urls", None)
            if asked is None:
                url_ok, url_detail = False, "the API records no URLs to check"
            else:
                missing = [w for w in want_urls
                           if not any(w in u for u in asked)]
                if missing:
                    url_ok = False
                    url_detail = ("no request asked for %s (asked: %s)"
                                  % (", ".join(missing), " | ".join(asked)))
        ok = ((got_fail == want_fail) and (len(nv) == want_nv)
              and (bool(harness) == want_harness_error)
              and (want_fail_text is None or _all_in(want_fail_text, text))
              and (forbid_fail_text is None or forbid_fail_text not in text)
              and url_ok)
        detail = ("as required" if ok else
                  "UNEXPECTED: fails=%d (want %s), not-verified=%d (want %d), "
                  "harness errors=%d (want %s)%s%s%s"
                  % (len(fails), ">=1" if want_fail else "0", len(nv), want_nv,
                     len(harness), want_harness_error,
                     "" if want_fail_text is None or want_fail_text in text else
                     "; the failure does not name %r" % want_fail_text,
                     "" if forbid_fail_text is None or forbid_fail_text not in text
                     else "; the failure wrongly blames %r" % forbid_fail_text,
                     url_detail))
        if not ok:
            for f in fails:
                print("        %s" % f)
            for n in nv:
                print("        NV: %s" % n)
            for n in harness:
                print("        HARNESS: %s" % n)
        cases.append((cid, what, ok, detail))

    run_case("POS-static", "the good tree passes every in-tree face",
             want_fail=False)
    run_case("POS-remote", "the good tree passes every published face",
             want_fail=False, api=FakeAPI(),
             expect_api_calls={"gh": 1, "zen": 1})
    run_case("F1-phantom-bump", "the least obvious face is bumped alone",
             {"docs/where-to-find-us.md":
              "# Synthetic\n\n| Version | 9.9.7 · released 2026-01-02 |\n"})
    run_case("F1-source-moved", "only the single source of truth moves",
             {"README.md": GOOD["README.md"].replace("v9.9.9", "v9.9.6")})
    run_case("F1-ambiguous", "two different canonical tags in one file",
             {"README.md": GOOD["README.md"] +
              "\nAlso canonical: the release tag `v9.9.1`.\n"})
    run_case("F2-concept-drift", "the concept DOI drifts in one file only",
             {".zenodo.json": GOOD[".zenodo.json"].replace("11111110",
                                                           "11111119")})
    run_case("F3-doi-swap", "the concept DOI is used in the version slot",
             {"README.md": GOOD["README.md"].replace(
                 "DOI **10.5281/zenodo.11111112**",
                 "DOI **10.5281/zenodo.11111110**")})
    run_case("F4-archive-label", "the archived version label drifts",
             {"INTEGRITY.md": GOOD["INTEGRITY.md"].replace("version 9.9.9",
                                                           "version 9.9.8")})
    run_case("F5-date-drift", "one of three release dates moves",
             {"CITATION.cff": GOOD["CITATION.cff"].replace("2026-01-02",
                                                           "2026-01-03")})
    run_case("F6-stray-token", "a foreign version token in a pure declaration",
             {"llms.txt": GOOD["llms.txt"] + "\nSupersedes 9.9.5.\n"})
    run_case("F7-missing-face", "a declaring file is deleted", drop=["llms.txt"])
    run_case("F7-reworded", "the source sentence is reworded so nothing matches",
             {"README.md": GOOD["README.md"].replace(
                 "release tag `v9.9.9`", "release marker `v9.9.9`")})
    run_case("R1-no-tag", "the declared canonical tag does not exist",
             api=FakeAPI(tag=False), expect_api_calls={"gh": 1})
    run_case("R2-no-release", "the tag exists but no Release was published",
             api=FakeAPI(release=False), expect_api_calls={"gh": 1})
    run_case("R3-not-deposited", "no Zenodo record carries the declared version",
             api=FakeAPI(records=[
                 {"doi": "10.5281/zenodo.11111111", "version": "9.9.8",
                  "published": True, "created": "2026-01-02T00:00:00Z"}]),
             expect_api_calls={"zen": 1})
    run_case("R3-cited-doi-absent", "the DOI cited in-tree is not a real record",
             api=FakeAPI(records=[
                 {"doi": "10.5281/zenodo.11111113", "version": "9.9.8",
                  "published": True, "created": "2026-01-02T00:00:00Z"},
                 {"doi": "10.5281/zenodo.11111114", "version": "9.9.9",
                  "published": True, "created": "2026-01-03T00:00:00Z"}]),
             expect_api_calls={"zen": 1})
    run_case("R3-version-mismatch", "the cited DOI carries another version",
             api=FakeAPI(records=[
                 {"doi": "10.5281/zenodo.11111112", "version": "9.9.8",
                  "published": True, "created": "2026-01-02T00:00:00Z"}]),
             expect_api_calls={"zen": 1})
    # The invariant the 0.1.2 release found missing. "A record carrying the release
    # version exists" and "the repository points readers at it" are two different
    # claims, and only the first was checked: this tree's archive line names the
    # previous version while the release version sits published beside it under the
    # same concept, which is the state the README was actually in on 2026-10-09.
    run_case("R3-archive-superseded",
             "the archive line points at a superseded record",
             {"README.md": GOOD["README.md"].replace(
                 "DOI **10.5281/zenodo.11111112**",
                 "DOI **10.5281/zenodo.11111111**").replace(
                     "version 9.9.9, 2026-01-03", "version 9.9.8, 2026-01-02"),
              "INTEGRITY.md": GOOD["INTEGRITY.md"].replace(
                  "DOI **10.5281/zenodo.11111112**",
                  "DOI **10.5281/zenodo.11111111**").replace(
                      "version 9.9.9, 2026-01-03", "version 9.9.8, 2026-01-02")},
             api=FakeAPI(), expect_api_calls={"zen": 1},
             want_fail_text="superseded archive")
    # --- Zenodo: a concept has two doors, and 2026-10-10 proved they differ ------
    # A concept read answers with a *record object*, and a version family answers
    # with an envelope -- both measured on 2026-10-10 against concept
    # 10.5281/zenodo.23051637. These fixtures mirror those two shapes, so the cases
    # drive the doors the code actually opens, in the order it opens them: the
    # concept read, then the version list, then the search (reported, never
    # decisive). Driving the real implementation rather than a stub that returns a
    # canned tuple is the point: a stub cannot express "the search came back empty
    # while the read did not", which is the shape of the defect.
    def _record_obj(recid, doi, version, versions_url=None):
        return json.dumps({
            "id": recid, "conceptrecid": "11111110", "doi": doi,
            "status": "published", "submitted": True,
            "metadata": {"version": version},
            "links": {"versions": versions_url or
                      "https://zenodo.org/api/records/%d/versions" % recid},
        })

    def _envelope(entries, total=None, nxt=None):
        return json.dumps({
            "hits": {"total": len(entries) if total is None else total,
                     "hits": entries},
            "links": ({"next": nxt} if nxt else {})})

    _v098 = {"doi": "10.5281/zenodo.11111111", "submitted": True,
             "created": "2026-01-02T00:00:00Z", "metadata": {"version": "9.9.8"}}
    _v099 = {"doi": "10.5281/zenodo.11111112", "submitted": True,
             "created": "2026-01-03T00:00:00Z", "metadata": {"version": "9.9.9"}}
    _family = _envelope([_v099, _v098])
    _none_found = _envelope([])
    # The 404 body, verbatim from the measurement of an id that is not there.
    _absent = json.dumps({"status": 404,
                          "message": "The persistent identifier does not exist."})

    # The case the 2026-10-10 CI run needed. R3 asked a *search* whether Zenodo held
    # anything; the search answered CI with a readable envelope holding nothing, and
    # the gate printed `no record under the concept` -- a claim about Zenodo's
    # holdings, made from an index that was silent, while the concept itself
    # resolved and its version family listed two published records. Here the search
    # door is empty and the read door is not, and the verdict must follow the read.
    run_case("R3-read-not-search",
             "an empty search is not evidence that a concept is empty (the read "
             "decides; the search is only reported)",
             api=_TransportAPI(outcomes=[
                 ("page", _record_obj(11111112, "10.5281/zenodo.11111112",
                                      "9.9.9"), 200),
                 ("page", _family, 200),
                 ("page", _none_found, 200)]),
             expect_api_calls={"zen": 3}, want_fail=False,
             forbid_fail_text="no record under the concept")
    # The question, not the answer. `10.5281/zenodo.23051637` does not end in
    # `23051637` -- it ends in `zenodo.23051637` -- so `zenodo_id()` returned the
    # whole segment and the gate spent its life asking `conceptrecid:zenodo.23051637`
    # and `/api/records/zenodo.23051637`: two well-formed questions about an id that
    # does not exist. Zenodo answered both truthfully (an envelope with
    # `hits.total = 0`; a 404), and every one of the 36 cases passed, because a fake
    # transport answers whatever it is handed. Three fixes examined the answer before
    # one of them printed the URL it had asked. This case pins the URL so the question
    # can never be wrong again without a case going red.
    run_case("R3-asks-the-right-id",
             "a Zenodo DOI is turned into the numeric id Zenodo indexes, not the "
             "whole last segment (`zenodo.<id>`)",
             api=_TransportAPI(outcomes=[
                 ("page", _record_obj(11111112, "10.5281/zenodo.11111112",
                                      "9.9.9"), 200),
                 ("page", _family, 200),
                 ("page", _family, 200)]),
             expect_api_calls={"zen": 3}, want_fail=False,
             want_urls=["/api/records/11111110",
                        "conceptrecid:11111110"]),
    # The counterpart with teeth. When Zenodo itself says the identifier does not
    # exist, the read *is* the evidence, and R3 must still be able to say no -- a
    # fix that made "empty" unreachable would have removed the gate's ability to
    # catch a deposit that gets deleted. Both halves are pinned: the claim, and the
    # 404 that justifies it.
    run_case("R3-concept-absent",
             "the concept read 404s, so the empty verdict is evidence-backed and "
             "the gate keeps its ability to say no",
             api=_TransportAPI(outcomes=[
                 ("reject", 404, _absent),
                 ("page", _none_found, 200)]),
             expect_api_calls={"zen": 2},
             want_fail_text=("no record at all under concept", "HTTP 404"))
    # And the same status answered by something that is not Zenodo. A 404 the probe
    # cannot read is a probe failure, not a deleted deposit -- the same distinction
    # as everywhere else in this file, at the one status where it is easiest to get
    # wrong, because 404 is the status a gate most wants to believe.
    run_case("R3-404-unreadable",
             "a 404 that is not Zenodo's own error body is read as a probe that "
             "cannot read, not a concept that is absent",
             api=_TransportAPI(outcomes=[
                 ("reject", 404, "<html><body>blocked by something in front</body>"
                                 "</html>"),
                 ("page", _none_found, 200)]),
             expect_api_calls={"zen": 1},
             want_fail_text=("cannot verify", "not with Zenodo's own error body"),
             forbid_fail_text="no record under the concept")
    run_case("R3-api-refused", "a rejected request is named, not called unreachable",
             api=_TransportAPI(reject=(400, json.dumps({
                 "status": 400, "message": "A validation error occurred.",
                 "errors": [{"field": "size", "messages": [
                     "Page size cannot be greater than 25. Please use "
                     "authenticated requests to increase the limit to 100."]}]}))),
             expect_api_calls={"zen": 1},
             want_fail_text="refused the request (HTTP 400)",
             forbid_fail_text="unreachable")
    # The 2026-10-09 remote run printed `R3 FAIL  no record under the concept`
    # against a concept that Zenodo's own API returns two published records for.
    # The query had not been refused and the network was up: the body simply was not
    # the shape this code assumes, and a chain of `.get(...)` calls turned an
    # unreadable page into an empty result -- the absence of a *field* recorded as
    # the absence of *records*. That is this catalogue's own subject matter, found in
    # this catalogue's own gate. The next two cases pin the distinction the fix
    # depends on at each door: a 200 we cannot read must never be reported as a
    # concept with nothing under it.
    run_case("R3-concept-shape", "a 200 at the concept door that is not a record "
             "object is not reported as an empty concept",
             api=_TransportAPI(outcomes=[
                 ("page", json.dumps({
                     "status": 200, "message": "shape this gate does not know"}), 200),
                 ("page", _none_found, 200)]),
             expect_api_calls={"zen": 1},
             want_fail_text="not with a record object",
             forbid_fail_text="no record under the concept")
    run_case("R3-versions-shape", "a 200 at the version door that is not a records "
             "envelope is not reported as an empty concept",
             api=_TransportAPI(outcomes=[
                 ("page", _record_obj(11111112, "10.5281/zenodo.11111112",
                                      "9.9.9"), 200),
                 ("page", json.dumps({
                     "status": 200, "message": "shape this gate does not know"}), 200),
                 ("page", _none_found, 200)]),
             expect_api_calls={"zen": 2},
             want_fail_text="not with a records envelope",
             forbid_fail_text="no record under the concept")
    # The counterpart, so the fix cannot pass by refusing to ever call a concept
    # empty: the read resolves, the version family is a real empty envelope, and that
    # must still be named as an empty concept.
    run_case("R3-family-empty", "the read resolves and the version family really is "
             "empty -- still named an empty concept (the shape check must not "
             "over-correct)",
             api=_TransportAPI(outcomes=[
                 ("page", _record_obj(11111112, "10.5281/zenodo.11111112",
                                      "9.9.9"), 200),
                 ("page", _none_found, 200),
                 ("page", _none_found, 200)]),
             expect_api_calls={"zen": 3},
             want_fail_text="no record at all under concept")
    # A transient upstream must not be reported as repository drift. The first case
    # feeds a 504 and then a good answer: before the retry existed, the first 504 was
    # the verdict. The second feeds a gateway that never recovers: the retry must not
    # become an exemption, and the finding has to say what it took.
    run_case("R3-retry-recovers", "a gateway timeout is retried rather than reported "
             "(the first answer was about the gateway, the second about the concept)",
             api=_TransportAPI(outcomes=[
                 ("reject", 504, "<html>504 Gateway Time-out</html>"),
                 ("page", _record_obj(11111112, "10.5281/zenodo.11111112",
                                      "9.9.9"), 200),
                 ("page", _family, 200),
                 ("page", _family, 200)]),
             expect_api_calls={"zen": 4}, want_fail=False)
    run_case("R3-retry-exhausted", "a gateway that never recovers still fails, and the "
             "finding states how many attempts were made",
             api=_TransportAPI(outcomes=[
                 ("reject", 504, "<html>504 Gateway Time-out</html>")] * 3),
             expect_api_calls={"zen": 3},
             want_fail_text="refused the request (HTTP 504) after 3 attempts")
    _filler = [{"id": 11110200 + i, "doi": "10.5281/zenodo.%d" % (11110200 + i),
                "submitted": True, "created": "2025-01-01T00:00:00Z",
                "metadata": {"version": "9.8.%d" % i}} for i in range(25)]
    run_case("R3-paginated", "a concept with more versions than fit on one page",
             api=_TransportAPI(outcomes=[
                 ("page", _record_obj(11111112, "10.5281/zenodo.11111112",
                                      "9.9.9"), 200),
                 ("page", _envelope(
                     _filler, total=27,
                     nxt="https://zenodo.org/api/records/11111112/versions?page=2"),
                  200),
                 ("page", _envelope([_v098, _v099], total=27), 200),
                 ("page", _envelope([_v098, _v099], total=27), 200)]),
             expect_api_calls={"zen": 4}, want_fail=False)
    run_case("R4-unprotected", "main is not protected",
             api=FakeAPI(protected=False), expect_api_calls={"gh": 1})
    run_case("R5-dead-required-check", "a required check no job reports",
             api=FakeAPI(contexts=["gates · python 3.9",
                                   "release face · the one nobody renamed"]),
             expect_api_calls={"gh": 1})
    run_case("R5-renamed-job", "a job was renamed and left a dead required check",
             {os.path.join(WORKFLOW_DIR, "gates.yml"):
              GOOD[os.path.join(WORKFLOW_DIR, "gates.yml")].replace(
                  "negative control · the manifest gate must be able to fail",
                  "negative control · renamed")},
             api=FakeAPI(), expect_api_calls={"gh": 1})
    run_case("R5-job-id-fallback", "a job with no name is matched by its id",
             {os.path.join(WORKFLOW_DIR, "gates.yml"):
              GOOD[os.path.join(WORKFLOW_DIR, "gates.yml")]},
             api=FakeAPI(contexts=["gates · python 3.12", "release-face"]),
             expect_api_calls={"gh": 1}, want_fail=False)
    run_case("R5-on-key-not-a-job", "an `on:` child key is not mistaken for a job "
             "(the required context `push` has no reporter and must fail)",
             api=FakeAPI(contexts=["push"]), expect_api_calls={"gh": 1})
    run_case("RV-unreachable", "a published face that cannot be run is a failure",
             api=FakeAPI(gh_broken=True), expect_api_calls={"gh": 1})
    run_case("R5-token-limited", "R5 reports NOT VERIFIED when the token has no "
             "admin read, and is counted rather than passed",
             api=FakeAPI(deny_protection=True), expect_api_calls={"gh": 1},
             want_fail=False, want_nv=1)
    # The canary must not be skippable: when the in-tree half already fails, the
    # published half never runs, so a case that expects a failure would otherwise
    # be credited on a stub it never called. This case asserts the harness
    # notices -- with the guard removed it reports no harness error and fails.
    run_case("CANARY-unskippable", "a case whose in-tree half already failed "
             "cannot be credited for a stub it never called",
             {"docs/where-to-find-us.md":
              "# Synthetic\n\n| Version | 9.9.7 \u00b7 released 2026-01-02 |\n"},
             api=FakeAPI(), expect_api_calls={"gh": 1}, want_fail=True,
             want_harness_error=True)

    print("verify_release_face --selftest")
    print("-" * 72)
    bad = 0
    for cid, what, ok, detail in cases:
        print("  %s %-24s %s" % ("+" if ok else "x", cid, what))
        if not ok:
            bad += 1
            print("      %s" % detail)
    print("-" * 72)
    if bad:
        print("selftest FAILED: %d of %d case(s) did not behave as required."
              % (bad, len(cases)))
        return 1
    print("selftest PASSED: %d cases -- every face is shown able to fail, the "
          "good tree passes both scopes, and a fake API that was never called is "
          "reported rather than trusted." % len(cases))
    return 0


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-path", default=".")
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    ap.add_argument("--no-remote", action="store_true",
                    help="in-tree faces only (the scope gate 17 runs)")
    ap.add_argument("--no-zenodo", action="store_true",
                    help="offline triage only; refused inside GitHub Actions")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    if args.no_zenodo and os.environ.get("GITHUB_ACTIONS") == "true":
        print("verify_release_face: --no-zenodo is refused in CI -- the published "
              "Zenodo face is the one nothing else checks, and a scope that can "
              "be narrowed in CI is a scope that will be.", file=sys.stderr)
        return 1

    rp = args.repo_path
    fails, not_verified, notes = [], [], []
    table = []

    print("= verify_release_face  scope=%s"
          % ("in-tree only (published faces run in release-face-remote.yml)"
             if (args.no_remote or not args.repo)
             else "in-tree + published (%s)" % args.repo))
    facts = run_static(rp, fails)

    if not args.no_remote and args.repo:
        table = run_remote(rp, args.repo, RealAPI(args.repo), facts, fails,
                           not_verified, zenodo=not args.no_zenodo, notes=notes)
    else:
        print("  scope note: R1..R5 were not run here. They are not skipped in "
              "general -- release-face-remote.yml runs the strict scope on a "
              "schedule and on every release.")

    # The in-tree ledger, printed from the extracted values rather than from the
    # absence of errors: an extractor that quietly stopped matching would
    # otherwise leave this section empty and still print a green verdict.
    print("-" * 72)
    print("  in-tree faces (what each declaring file actually says)")
    claims = facts.get("_claims") or {}
    for name in DECLARING:
        print("    %-24s %s" % (name, claims.get(name, "(unreadable)")))
    print("    %-24s %s" % ("release date",
                            " ".join("%s=%s" % kv for kv in
                                     sorted((facts.get("_dates") or {}).items()))
                            or "(unreadable)"))
    print("    %-24s %s" % ("concept DOI", facts.get("concept") or "(unreadable)"))
    print("    %-24s %s @ %s   [README.md=%s INTEGRITY.md=%s]"
          % ("archived DOI / version", facts.get("archived_doi"),
             facts.get("archived_version"),
             (facts.get("_ver_doi") or {}).get("README.md"),
             (facts.get("_ver_doi") or {}).get("INTEGRITY.md")))

    if table:
        print("-" * 72)
        print("  published faces")
        for rid, what, verdict, msg in table:
            print("    %-4s %-40s %-13s %s" % (rid, what, verdict, msg))
    print("-" * 72)
    for f in fails:
        print("  FAIL %s" % f)
    for n in not_verified:
        print("  NOT VERIFIED %s" % n)
    for n in notes:
        print("  note %s" % n)
    print("-" * 72)
    if fails:
        print("verdict: FAIL -- %d finding(s), %d not verified"
              % (len(fails), len(not_verified)))
        return 1
    if not_verified:
        print("verdict: PASS on what could be checked; %d face(s) NOT VERIFIED "
              "(named above, not counted as PASS)" % len(not_verified))
        return 0
    print("verdict: PASS -- every face tells the same story")
    return 0


if __name__ == "__main__":
    sys.exit(main())
