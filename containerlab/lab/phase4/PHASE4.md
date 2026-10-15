# Phase 4 — the curriculum, as machine states: PASSED (2026-07-31)

The plan's Part A–D arc now runs end to end on a five-AS topology plus an
attacker. Every step below was executed and observed; the outputs quoted are
real. What is **not** done yet is the notebook — this phase proves the lab can
produce each state on demand, which is what Phase 5 will wrap in markdown.

## What runs

`bgpsec-p4.clab.yml` — the Phase 3 chain with two additions, plus four config
sets the lab switches between:

```
AS64602 ── AS64601 ── AS64603 ── AS64604 ── AS64605     AS64666
 origin     transit    transit    transit    observer    attacker
   Q           Q          Q          Q       GoBGP-SRx      Q
                                        └───────────────────┘
```

```
lab/tools/gen_configs.py     topology + part flags -> 6 configs x 4 parts
lab/tools/set_part.sh        swap configs/active/, restart daemons in place
lab/tools/add_router_key.sh  add an ASN to the lab-owned key vault
lab/tools/vty.sh             drive QuaggaSRx's VTY without vtysh or sudo
lab/phase4/keys/             lab-owned vault: the four testbed keys + 64601, 64666
```

Krill signs all six CSRs at deploy time (`Added certificate for AS646xx`, six
lines) and Routinator serves six router keys, because `sign_csr.sh` just walks
the vault's `ski-list.txt` — adding an AS needs no change to the RPKI plane.

## Two deviations from the plan's topology, both forced

**A fifth legitimate AS.** The attacker's forged path is always exactly two
hops (`64666 64602`), so it only wins where the real path is longer. In the
plan's four-AS chain the real path also reaches AS64604 in two hops: the two
tie, the tie breaks on router-id, and the attack fails for a reason that
teaches nothing. AS64601 makes the real path three hops and the forgery wins
on merit. Measured both ways before changing it.

**The attacker peers with AS64604, not AS64605.** Tried it at the observer
first, since the plan's rationale is proximity. It works for Parts A and B —
but AS64605 is GoBGP-SRx, and while it *marks* a bad path it has no policy
that can act on one, so in Part C it labelled the forgery and used it anyway.
QuaggaSRx has `srx policy bgpsec ignore invalid`. The victim therefore has to
be a QuaggaSRx router, and AS64604 is the only one far enough from the origin.

A useful correction fell out of the first attempt: the plan's table says
GoBGP-SRx has "no RTR integration". That is true of *router key* PDUs, which it
reads from the local vault — but it keeps upstream GoBGP's RTR client, so it
does full ROV against Routinator (`gobgp rpki server` → session Up, VRP count
tracking Krill). The observer's status column is `<origin>,<bgpsec>`.

## Part-by-part evidence

State is switched with `set_part.sh <dir> a|b|c|d`; RPKI-side state (ROAs,
certificates) survives the switch, which the narrative depends on.

**Part A — unprotected.** Baseline `(-,-,-)` with status `D`, SRx evaluation
off everywhere.

| Step | Observed at AS64604 | At the observer |
|---|---|---|
| baseline | `*> 10.64.2.0/24 … 64603 64601 64602` | same path, 4 hops |
| A2 origin hijack | `*> … 10.46.0.6 … 64666` — attacker wins on path length | follows the attacker |
| A3 path forgery | `*> … 10.46.0.6 … 64666 64602` | `64604 64666 64602` |

**Part B — ROV.** ROA `10.64.2.0/24 => 64602` issued in Krill; Routinator VRP
count 0 → 1 and the routers pick it up in ~25 s.

| Step | Observed |
|---|---|
| B6 legit route | `(v,-,-)` LocPrf 120 — origin Valid |
| B7 replay hijack | `(i,-,-)` status **`I`** — received, marked Invalid, ignored; the real route stays best |
| B8 replay forgery | `(v,-,-)` LocPrf 120, **wins** — ROV rates the forgery Valid |

B8 is the pivot the whole curriculum turns on, and it lands: the same
validation that just killed the hijack authorises the forged path, because the
origin it names is the authorised one.

**Part C — BGPsec.**

| Step | Observed |
|---|---|
| baseline | `(v,v,-)` LocPrf 140 — both validations pass, both +20 policies fire |
| C12 replay forgery | `(v,i,-)` status **`I`** — origin still Valid, path Invalid, route dropped |
| observer | real 4-AS path with `{bgpsecs}`, `V,V` |

AS64666 holds a genuine Krill-issued router certificate and signs with it. It
still cannot produce AS64602's signature, which is the entire point of step 12.

**Part D — partial deployment.** The gap is at the origin, and that is a
finding rather than a preference — see below. The route survives to the
observer carrying no BGPsec attribute at all:

| Where | Observed |
|---|---|
| AS64601 (first signer) | `(v,i,-)` LocPrf 100 |
| AS64604 | `(v,i,-)` LocPrf 100, path `64603 64601 64602` |
| AS64605 | `V,N` — origin Valid, **no `{bgpsecs}`** |

So the observer can still prove who originated the prefix and nothing whatever
about the path it took. That is step 15's question, in one line of output.

## Findings

- **BGPsec cannot be toggled on a live session.** Removing `neighbor X bgpsec
  both` from both ends and clearing the session leaves bgpd still emitting
  BGPsec-shaped UPDATEs; the peer answers "Missing well-known attribute 3" and
  the session sits in Idle forever. The setting only takes at daemon start.
  This is why the images now run `run-daemon.sh` as PID 1 — `pkill -x bgpd`
  restarts the daemon against an edited config while the container, its veths
  and its addresses survive. `docker restart` would destroy the links
  (PHASE3.md). **Both router images were rebuilt for this**; `IMAGES.md` needs
  updating before the tarball is redistributed.

- **A signing QuaggaSRx cannot talk plain BGP to one neighbour.** With
  `srx bgpsec active` set it signs on *every* session regardless of the
  per-neighbour setting — `bgpsec rec` ("send BGP4 only") and omitting the line
  entirely both tested, both still sign, both break the session. This is why
  Part D's gap sits at the origin rather than mid-chain as the plan asks:
  signing → plain is the direction that breaks, plain → signing works. A
  mid-chain gap would need a non-QuaggaSRx router in that position.

- **An unsigned route on a BGPsec session scores Invalid, not unknown.** So
  `ignore invalid` in Part D would silently disconnect every AS that has not
  deployed BGPsec. Part D therefore de-prefers instead of dropping, which is
  what an operator would really do — and is a sharper answer to step 17 than
  the synthesis question expects.

- **GoBGP marks but does not act.** Origin validation alone changed nothing
  until an explicit `rov-drop-invalid` import policy was added to the observer's
  config. Worth showing students directly: the validator's opinion and the
  router's behaviour are two different things.

- **10.0.0.1 is the mgmt bridge gateway.** AS64601 failed to start with
  "Address already in use" until it moved to 10.0.0.7.

- **Convergence is slower than it looks.** Several checks read a stale table
  because 20 s was not enough after a config change; 30 s was. Assertion cells
  must poll, not sleep — `labkit.py` needs a `wait_for_path()` helper or the
  notebook will produce intermittent wrong answers.

## State after this phase

Lab **running**, part **d** active, one ROA in Krill, no attack announced (a
part switch restarts the daemons, which drops the attacker's runtime
announcements — re-applying them is the "replay attack N" step in each part).

Next: Phase 5 — `labkit.py` around `vty.sh`, `rtr_query.py`,
`bgpsec_dissect.py` and the polling helpers, then the notebook itself.
Before that, two loose ends: refresh `IMAGES.md` and the distributable tarball
for the rebuilt router images, and re-verify the Phase 3 signature-growth
capture on this topology, where it should now show four signatures rather than
three.
