# SF-016 · Swallowed failure returned as the result

**Status**: `draft` ｜ **Family**: A · Vacuous Verification ｜ **Confidence**: medium ｜ **as of** 2026-11-12

> **One line.** The value a failed operation was supposed to produce never exists, and the enclosing function returns it anyway — so the caller receives "the result" without being told it was never computed.

## Symptom

`SF-003` deletes the failure signal. `SF-004` substitutes a fake value. This one is the step after both: the signal is deleted *and* the unset name is handed back across the function boundary, so the absence leaves the place where it could have been noticed.

```python
def load_config(path):
    try:
        cfg = json.load(open(path))
    except OSError:
        pass
    return cfg                  # UnboundLocalError, or a stale/None value
```

What the operator sees: the consumer of `load_config` behaves as if a config had been read. No log line, no exception, no metric. The failure is not merely quiet — it has been *routed downstream* in the shape of a value.

Two forms that survive review more easily:

```python
# variant B — initialise to the "empty" value, then swallow
cfg = None
try:
    cfg = json.load(open(path))
except OSError:
    pass
return cfg                      # None travels out; callers treat None as "no config", not "could not read"
```

```python
# variant C — the details field
token_details = None
if row[3]:
    try:
        token_details = json.loads(row[3])
    except ValueError:
        pass
return {"tokens": n, "details": token_details}   # malformed details are indistinguishable from "no details"
```

Variant C is the subtle one: `None` is a legal value for an *advisory* field, so nothing crashes and the loss is permanent — the record now claims the details were absent rather than unreadable.

## Why it is silent

Of the four parts — *something to check*, *a way for absent to count*, *a signal that can prove the claim*, *an oracle that keeps discriminating* — the third is destroyed twice over. The exception channel is closed by the handler, and the value channel is closed by the `return`: the caller's own type check (`is None`, `if cfg`, `dict.get`) has already been taught that "absent" is a normal answer.

Nothing else notices because both halves are locally reasonable. The handler is written as resilience; the `return` is written as a plain function contract. Only their composition is the failure, and composition is exactly what review reads one line at a time.

The discriminating question is not "was the exception swallowed" but **"does the swallowed failure reach a verdict, a return value, or an exit code"**. A handler that logs a best-effort cleanup and returns something it computed elsewhere is not this pattern; a handler whose uncomputed name is the return value is.

## Minimal reproduction

```python
import json

def load_config(path):
    try:
        cfg = json.load(open(path))
    except OSError:
        pass
    return cfg

print(load_config("/nonexistent/config.json"))
```

Observed: `UnboundLocalError: cannot access local variable 'cfg'` — or, once `cfg` is pre-initialised, `None` with **no** error and no log. Expected after fix: `None` **plus** a recorded reason, so the caller can distinguish "no config" from "could not read the config".

## Self-check

1. For every `except` whose body only `pass`es / `continue`s / logs with no counter, ask: *which name was the `try` body computing, and does this function return it?* Two lines of reading per hit.
2. `gate-lint` automates exactly that question as `SFL-007`:

```bash
python tools/gate-lint.py path/to/src --no-tree --json    # findings with rule SFL-007 name the variable
```

3. The noise floor matters, so state it. On two unmodified third-party trees (`openai-agents-python` `src/agents`, 317 files; `mcp` `python-sdk` `src/mcp`, 128 files) the shape rules returned **374** findings, of which `SFL-007` returned **13** — a reading list, not a bug list. All 13 were read; **none** was a defect:

| Site | Reading |
|---|---|
| `middleware/…/advanced_sqlite_session.py` ×4 | advisory `*_details` default to `None`; `None` is a legal value |
| `extensions/memory/encrypt_session.py:81` | documented dual-format key acceptance (Fernet key *or* raw string) |
| `extensions/memory/redis_session.py:759` | drops corrupted messages and keeps scanning — the `return` sits on the success path |
| `extensions/sandbox/vercel/_provider.py:146` | declared best-effort cleanup, with the comment saying so |
| `extensions/sandbox/vercel/sandbox.py:213` | documented: acknowledgement must not become authorization |
| `memory/sqlite_session.py:510` | same class as `redis_session` |
| `run_state.py:3057`, `:1767` | docstring-declared best-effort serialization with a fallback |
| `server/auth/handlers/authorize.py:110` | RFC 6749 §4.1.2.1 behaviour: never redirect to an invalid URI |
| `server/request_state.py:380` | handler calls a `NoReturn` helper that raises — fail-closed, not swallowed |

Two of the thirteen are false positives of the *mechanism*, not judgement calls: the `return` living inside the `try` body, and a handler whose callee raises. Both are disclosed rather than tuned away, because a rule that silently excludes "functions that look like they raise" is the same failure this catalog documents.

## Fix

Record the failure, and make the return conditional on it.

```python
def load_config(path, problems):
    try:
        return json.load(open(path))          # success returns here
    except OSError as e:
        problems.append((path, repr(e)))      # recorded, counted
        return None                           # None now means "failed", and the caller knows why
```

The caller's side matters as much: `None` must not be indistinguishable from a legitimate empty result, so either return a discriminating type or require the caller to consult `problems`.

| Negative control | Expected result |
|---|---|
| Point `path` at a file that cannot be read | `problems` is non-empty and the caller sees `None` *with* a reason; run exits non-zero |
| Point `path` at a file containing `{}` | `problems` is empty and `None` is **not** returned — an empty config is not a failure |
| Make one advisory field malformed (variant C) | the record carries an "unreadable, not absent" marker; the value does not silently become `None` |

A fix without a negative control is not a fix — see `CONTRIBUTING.md`.

## Related

- `SF-003` — the same handler, before the value leaves the function: the failure signal dies, but nothing is returned as a result
- `SF-004` — a sentinel is returned on purpose; here the returned value was never computed at all
- `SF-006` — what is not declared is not checked; the same erasure applied to fields instead of exceptions
- External: *error handling* guidance in the language's standard library, and mutation testing as the way to prove the fixed handler still fails when it should
- Taxonomy: [`../docs/taxonomy.md`](../docs/taxonomy.md)

---

## 中文要点

- **一句话**：本该由失败的那一步产出的值根本没算出来，函数却照常返回，调用方拿到的是"结果"，而不是"没算出来"。
- **为什么会静默**：异常渠道被 `except` 关掉，值渠道被 `return` 关掉——调用方的 `is None` 检验早已被教会"absent 是正常答案"。两侧单看都合理，错在组合。
- **怎么自查**：对每个只 `pass` / 只记日志的 `except` 问一句：`try` 里在算什么名字？本函数是否把它返回了？`gate-lint` 的 `SFL-007` 就自动问这一句并点名变量。
- **修法要点**：先记录再返回；`None` 必须与"合法空值"可区分；负对照要覆盖"读不到"与"读到空"两种情况，二者结果必须不同。
