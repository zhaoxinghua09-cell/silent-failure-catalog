# SF-014 · Zombie process looks alive

**Status**: `stable` ｜ **Family**: E · Process & Environment ｜ **Confidence**: high ｜ **as of** 2026-09-19

> **One line.** A hung process reports no error, holds no CPU and never exits — so every liveness signal says it is fine.

## Symptom

A long-running job stops making progress. It does not crash, does not log an error, and does not exit. Every check built on "is the process there?" answers yes.

A representative observation:

```
pid 41208   age 19h   CPU time 0   RSS 0.25 MB   last output: 18h ago
status: running
```

Four independent signals all point the wrong way:

| Signal | Reading | Naive conclusion |
|---|---|---|
| process exists | yes | it is working |
| exit code | none | it has not failed |
| stderr | empty | no errors |
| CPU time | 0 | idle, presumably waiting |

The actual state is *stuck*. The job will never finish, and nothing will report that.

**Compounding variant:** the orchestration layer accumulates process groups it never reaps. Spawning the same job five times leaves five live groups — each with its own set of child processes — and the old ones never exit. A fixed 15 processes per group becomes 75 resident processes, most of them zombies. Now even the resource accounting is misleading, because the zombies hold memory and PIDs while contributing nothing.

## Why it is silent

*A signal that can prove the claim* is missing. Liveness is being inferred from **existence**, and existence is the one property a hung process keeps.

This is Family E: the logic that asked "is it running?" is correct, and the environment gives an answer that is technically true and operationally useless.

Two design factors make it durable:

1. **Absence-based status.** "No error" and "no exit" are read as success. There is no positive progress signal to contradict them.
2. **No timeout.** A job with no deadline can be in its valid states forever, so "still running" and "stuck" are indistinguishable by construction.

## Minimal reproduction

```python
import subprocess, time

p = subprocess.Popen(["python", "worker.py"])       # worker blocks on a dead socket
time.sleep(1)
print("alive:", p.poll() is None)                   # → True
time.sleep(60 * 60)
print("alive:", p.poll() is None)                   # → still True, still no output
# and nothing anywhere has reported a problem
```

Observed: `alive: True` indefinitely, no error, no exit — Expected after fix: a timeout kills it and reports `stalled: no output for 600s`

## Self-check

Three questions, all cheap:

1. **When did it last make progress?** Not "is it alive" — "when was the last output, the last heartbeat, the last state change?"
2. **Is there a deadline?** If any job can run forever without complaint, it has no failure mode.
3. **Are child processes reaped?** Compare the expected process count against the observed count. A number that only grows is a leak.

A sharper form of (1): **define progress in the code**, not in the observer's head. "Last output timestamp" is a progress signal; "process is running" is not.

## Fix

Add positive progress signals, timeouts and reaping — and make the absence of progress a failure.

```python
DEADLINE      = 600        # seconds of silence before declaring a stall
HEARTBEAT     = 30         # expected interval

last_progress = time.monotonic()

with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                      start_new_session=True) as p:      # own process group → reaping
    try:
        for line in p.stdout:
            print(line.decode(errors="replace"), end="")
            last_progress = time.monotonic()             # positive progress signal
            if time.monotonic() - last_progress > DEADLINE:
                os.killpg(os.getpgid(p.pid), signal.SIGKILL)
                raise RuntimeError(f"stalled: no output for {DEADLINE}s")
    finally:
        p.wait(timeout=10)                                # never leave it behind
```

Principles, in order of importance:

- **Progress, not existence.** Every job should emit something that proves it is advancing; the watchdog keys on that, never on `poll() is None`.
- **Every job has a deadline.** An unbounded job has no way to fail.
- **Kill the process group, not the process.** Children survive a bare `p.kill()` and become the zombies in the compounding variant.
- **Always reap, in a `finally`.** Leaked groups make resource accounting lie.
- **Report stalls distinctly from failures.** A `stalled` outcome and a `crashed` outcome need different responses; collapsing them into "did not finish" loses the information.

| Negative control | Expected result |
|---|---|
| Make the worker hang on purpose | watchdog kills it and reports `stalled`, with the silence duration |
| Run the worker 5 times in sequence | resident process count returns to baseline — no accumulation |
| Run a healthy worker | completes normally, no false stall |

## Related

- `SF-008` — the same error class one level up: existence used as evidence of behaviour
- `SF-013` — the other Family E entry: environment state of files, not processes
- Established practice: watchdogs keyed on heartbeats; `start_new_session` / process groups; `pytest-timeout`
- Taxonomy: [`../docs/taxonomy.md`](../docs/taxonomy.md) § E

---

## 中文要点

- **一句话**：进程卡死了，但**不报错、不退出、不占 CPU** —— 于是"它还活着吗"这个检查永远答"活着"。
- **为什么会静默**：用**存在**推断**存活**，而"存在"恰好是卡死进程唯一还保留的属性。两个设计因素让它长期潜伏：① **否定式状态**（"没有错误""没有退出"被读成正常，没有任何正向进展信号来反驳）；② **没有超时**（无期限的任务可以在合法状态里待一辈子，"仍在运行"与"已经卡死"在构造上不可区分）。
- **复合变体**：编排层**不回收**进程组 —— 同一任务跑 5 次就留下 5 组，每组固定十几个子进程，旧的一个不退。此时连资源账目都在骗人。
- **怎么自查**：三问 —— ① 它**最后一次取得进展**是什么时候？（别看"是否存活"，看"最后输出/心跳/状态变化"）② **有期限吗**？（能永远跑而不报怨的任务，没有失败模式）③ **子进程回收了吗**？（进程数只增不减 = 泄漏）
- **修法要点**：进展信号（不是存在信号）+ 期限 + **杀进程组而不是杀进程** + `finally` 里必须 `wait` 回收；`stalled` 与 `crashed` 要分开报。
- **反向对照**：故意让 worker 挂住 → 看门狗必须杀掉并报出静默时长；连续跑 5 次 → 常驻进程数必须回到基线。
