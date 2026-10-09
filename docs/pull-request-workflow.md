# Why a pull request is not optional here

**as of 2026-10-09**

`main` requires three status checks, and they are enforced against administrators as well as
anyone else. This file exists because the obvious way to work in this repository stopped working
on 2026-10-09, and the reason is worth writing down.

---

## What changed, and what it means for you

| | before 2026-09 | after 2026-10-09 |
|---|---|---|
| Required status checks | declared | declared |
| Administrators | bypassed them | **bound by them** (`enforce_admins`) |
| Required branch up to date | no | **yes** (`strict`) |
| So a direct push to `main` | went through, with a bypass notice | **is rejected** |

The bypass notice used to look like this, and it was easy to read as harmless:

```
remote: Bypassed rule violations for refs/heads/main:
remote: - 3 of 3 required status checks are expected.
```

Those three checks **were** evaluated on that push. The push was allowed anyway, by an
administrator, and the mismatch was recorded rather than enforced. Nothing about the checks
changed; only who was exempt did.

---

## The shape that cannot work

Consider a workflow whose only trigger on `main` is `push`:

```
on:
  push:
    branches: [main]
```

Required status checks are evaluated **after** a commit exists. So the order is always wrong:

1. you push a commit to `main`
2. GitHub asks: do the three required checks pass **for this commit**?
3. the run has not started yet — it starts *because of* this push
4. the checks are not passing, so the push is rejected
5. the run that would have passed them never got a chance to start

This is not a misconfiguration. It is the two rules contradicting each other. No setting
combines them into something that works, because the trigger is the thing being blocked.

---

## What to do instead

Push a branch, open a pull request, let the checks run there, merge.

```
git checkout -b <short-description>
# ... work, commit as usual ...
git push -u origin <short-description>
```

Then open the pull request against `main`. All three checks run on the pull request, and the
merge is permitted once they pass. `gates.yml` already lists `pull_request` among its triggers,
so this works today without editing any workflow.

Three checks must pass, and their names are load-bearing — a required check is matched by name:

- `gates · python 3.9`
- `gates · python 3.12`
- `negative control · the manifest gate must be able to fail`

---

## Branches are not protected

Only `main` carries these rules. A branch push is unrestricted, so the loop above has no
chicken-and-egg problem: the work lands on the branch first, and only the merge touches `main`.

## Tags are not protected either

`v0.1.0` and `v0.1.1` exist, and `gates.yml` also runs on `tags: ["v*"]`. Tag pushes are not
governed by branch protection, so cutting a release tag is unaffected by any of the above.
