# Phase 5 — `labkit.py` and the notebook: PASSED (2026-07-31)

Exit criterion from the plan: *a student who has never seen the lab runs the
notebook top-to-bottom on a clean machine and reaches the end without external
help.* Met — the notebook executes end to end with no intervention, and every
assertion in it passes. Evidence below.

## What ships

| | |
|---|---|
| `bgpsec-lab.ipynb` | the deliverable — 88 cells, Parts A–D with synthesis questions |
| `bgpsec-lab-instructor.ipynb` | the same plus model answers and teaching notes |
| `labkit.py` | ~790 lines: deploy, drive, inspect, assert |
| `reset.sh`, `README.md` | operational wrappers |
| `tools/build_notebook.py` | generates both notebooks from one source |
| `tools/smoke_test.py` | drives all four parts headless, ~11 min |
| `tools/run_notebook.py` | executes a notebook the way a kernel would |
| `configs/srx_server.conf` | lab-owned, all routers pre-mapped |
| `overlay/srx-server.Dockerfile` | supervisor for the validation engine |
| `phase4/clab-bgpsec-p4/graph/` | `containerlab graph` dot and mermaid output (regenerated on demand — containerlab recreates this directory on every deploy) |
| `dist/bgpsec-lab-images.tar.gz` | 275 MB, regenerated for the rebuilt images |

Both notebooks are generated. Editing the `.ipynb` directly would let the
student and instructor copies drift, and a stale instructor copy is worse than
none because it is trusted.

## Design decisions

**Python cells throughout, no `%%bash`.** The plan proposed a Python 3 kernel
with `%%bash` cells. In practice every useful action needs its result parsed —
a validation state, an AS path, a signature count — and a `%%bash` cell can
only print. Since the plan also wanted the repeated operations hidden in
`labkit` so exercise cells read as pedagogy rather than plumbing, those two
pull the same way: `lab.attack("forge")` says more than the eight lines of
telnet-into-a-VTY it replaces. Every shell command the lab runs is still
visible, in `labkit.py`, for students who want to look.

**Parse the detail view, not the table.** `show ip bgp` has ambiguous columns —
AS numbers, metric, local preference and weight are all bare integers with no
dependable alignment, so a parser cannot tell where the path starts.
`show ip bgp <prefix>` puts the AS path on its own line, spells validation
results out in words, and — discovered late, and worth the rework — carries the
whole BGPsec signature chain with a SKI per hop. That last one turned into a
teaching cell: the router shows which key it checked each hop against, and the
SKIs match both the vault and the Router Key PDUs the validator serves. Three
independent sources of the same identity, which is exactly what the plan's
step 11 asked for.

**Poll, never sleep.** Every wait polls for its condition. Timings measured
during development ranged from 20 s to 35 s and were not stable, and a cell
that reads the table too early reports a confident wrong answer.

**`wait_for_route` is distinct from `wait_for_best`,** and the distinction is
the subtlest thing in the file. Once a defence is on, the attack still
*arrives*, it just stops being *used*. Waiting for it to become best would hang
forever; not waiting at all races the announcement and reports that the attack
was never mounted. This produced a real false failure — "the forgery never made
it into the table" — before it was fixed. `settled=True` additionally waits for
the router to have finished judging, since a path appears in the table a moment
before the validator has answered for it.

**`check()` prints, it does not raise.** A failed assertion should tell the
student what is wrong and let them keep reading, not abort the notebook.
`checkpoint()` then summarises and says plainly whether it is safe to continue.

## Findings

- **SRx-server keeps stale client registrations, and that silently kills the
  lab.** Its client table is keyed by proxy ID and outlives the router that
  registered. Every part switch restarts five QuaggaSRx routers; a router
  coming back against its own stale entry never completes the handshake, so
  every validation result returns `undefined` — and QuaggaSRx's *default*
  `srx policy origin ignore undefined` then drops the route. The symptom is a
  lab where every session is Established and no router has any routes, with
  nothing in any log that names the cause. Four changes were needed:

  1. an overlay giving `srx_server` the same PID-1 supervisor the routers have,
     so it can be restarted in place;
  2. `set_part.sh` restarts it *first*, so routers register into a clean table;
  3. routers restart staggered — five simultaneous handshakes was enough to
     lose one even against a clean table;
  4. a lab-owned `srx_server.conf` that pre-maps every router, since upstream's
     copy names only the two that its own two-router topology needed.

  And a fifth, defensive: the generated configs now set
  `no srx policy origin ignore undefined` explicitly. Failing open on validator
  loss is both what an operator would choose and what stops a transient hiccup
  from looking like a broken lab.

- **Key revocation works, and is more dramatic than expected.** Removing
  AS64602's BGPsec definition from Krill drops Routinator from six router keys
  to five, and the route does not merely become invalid — it disappears from
  AS64604's table entirely, because Part C drops what it cannot verify.
  Meanwhile AS64602 carries on signing with the same key, unaware. This is now
  exercise C13, which the plan asked for and earlier phases had deferred.

- **GoBGP's JSON output omits validation state.** `gobgp -j global rib` gives
  clean structured output with no origin or BGPsec result in it, so the
  observer is read from the text table instead. Its age column is bare digits
  and colons, exactly like an AS number, so the age pattern has to be pinned to
  `HH:MM:SS` — without that the parser silently truncates the AS path and
  succeeds with a wrong answer.

- **`nbconvert` is not installed on this host.** Rather than adding packages to
  a machine that is meant to be a student's, `tools/run_notebook.py` executes
  the cells in one shared namespace the way a kernel does. One gotcha:
  Python puts the *script's* directory on `sys.path` while Jupyter puts the
  *notebook's*, so `import labkit` has to be made to match the kernel.

## Verification

The full notebook, executed top to bottom from a cold deploy, with no
intervention:

```
46 code cells, 0 raised, ~15 min
```

Every checkpoint passed: A1, A2, A3, B6, B7, B8, C11, C11 identity,
C11 capture, C12, C13, D15. The exercises that matter most:

| | Observed |
|---|---|
| A2 hijack | AS64604 sends traffic for the prefix to AS64666 |
| A3 forgery | forged two-hop path wins, reaches the far end |
| B7 | hijack rated Invalid, dropped by policy, real route restored |
| **B8** | **forged path rated Valid and used — ROV defeated** |
| C11 | signature block grows 1 → 2 → 3 → 4 across the four links |
| C11 identity | every in-path SKI matches the key the RPKI publishes |
| C12 | forgery rated `(valid, invalid)` and dropped; ROV still fooled |
| C13 | revoking one certificate removes the route entirely |
| D15 | route survives the gap, unverifiable, de-preferred |

`tools/smoke_test.py` drives the same four parts headless in about eleven
minutes and is the fastest way to tell whether a change broke an exercise.

## Loose ends

- **`tshark` is still absent from this host.** The lab does not need it: the
  notebook dissects captures with `lab.dissect()`, which uses the lab's own
  parser. The Wireshark GUI remains an optional exploration step, and the plan's
  §5 claim that a packaged `tshark` would be available should be read as
  aspirational rather than verified.
- **The plan's §7 assumption is still unsettled** — whether students run this
  locally or share a server. Everything here assumes local. A shared host would
  need per-student lab-name prefixes and management subnet separation, which is
  a change to the topology file and `labkit`'s node naming, not to the
  curriculum.
