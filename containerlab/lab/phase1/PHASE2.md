# Phase 2 — RPKI plane: PASSED (2026-07-30)

Exit criteria from the plan: *Routinator serves the testbed TAL over RTR and
the routers show a synced cache.* Met, plus a full ROA lifecycle round-trip.

The two-router topology in this directory serves Phases 1 and 2: the Phase 1
port already carried the whole Krill → krillc → tal_share → Routinator → SRx
chain with staged ordering, so Phase 2 was verification plus one config
decision. Phase 3 gets its own topology file.

## Config decision: lab-owned routinator.conf, refresh = 30

`lab/configs/routinator.conf` replaces the upstream bind (upstream file
untouched). Only change: `refresh = 30`. Routinator's 600s default means a
ROA issued in Krill takes up to 10 minutes to reach the routers — unusable
for the Part B ROA-lifecycle exercise and for interactive verification.
Measured end-to-end propagation with 30s: **~25 seconds** from `krillc`
command to SRx cache change, both for issue and withdrawal.

## Verification evidence

**RTR service** — queried directly with `lab/tools/rtr_query.py` (minimal
RFC 8210 v1 client, host-side, no container tooling needed —
`python3 rtr_query.py 10.0.0.14 3323`):

- Reset Query returns Cache Response + **4 Router Key PDUs** — the exact
  ASN↔SKI pairs from `ski-list.txt`, each with an 89-byte P-256 SPKI —
  then End of Data.
- Serial advances with CA-side changes: 0 (initial) → 1 (ROA added, IPv4
  Prefix PDU `10.2.0.0/16-16 => AS64602` appears) → 2 (ROA removed, PDU gone).

**Synced router cache** — the routers delegate to srx_server, so "the
routers' cache" is SRx's cache plus the proxy sessions:

- SRx console (`telnet 10.0.0.15 17901`, no password despite the config's
  `password = "x"`): `show-proxies` lists both routers as
  `active/pre-conf` proxies (0x0A000002 = as64602, 0x0A000003 = as64603),
  `num-updates` = 4.
- Router keys land in the crypto API: "RPKI/Router Key Stored in
  srxcryptoapi" (srx_server log).
- Signed UPDATEs re-verified on the wire after redeploy (fresh pcap: two
  BGPsec_PATH attrs, sender SKI at the RFC 8205 offset).

**ROA round-trip** (the CA→validator→cache loop, both directions):

| Step | Observed |
|---|---|
| `krillc roas update --add "10.2.0.0/16 => 64602"` | ROA listed in Krill |
| Routinator picks it up | `routinator_ta_valid_vrps_total` 0 → 1; `/json` shows the ROA |
| RTR delivers it | serial 1, `IPv4 Prefix 10.2.0.0/16-16 => AS64602 (announce=1)` |
| SRx applies it | prefix cache 0 → 1 entries |
| `--remove` the ROA | Routinator VRPs → 0 in 24s; RTR serial 2 |
| SRx withdraws it | log: Serial Notify → `ROA-wl: Wd` → "Remove ROA entry!" — 23s after the remove command |

The sync is **notification-driven**: Routinator sends RTR Serial Notify on
new data; SRx serial-queries immediately. The 30s refresh bounds only the
Krill→Routinator leg.

## Gotchas found (notebook-relevant)

- SRx console `num-prefixes` counts **allocated prefix nodes, not active
  ROAs** — after a withdrawal it stays at 1 (empty node). Assertion cells
  must not use it to check ROA state; use Routinator metrics
  (`routinator_ta_valid_vrps_total`) or the SRx log lines instead.
- Routinator 0.15 VRP metrics are `routinator_ta_valid_vrps_total{name="ta"}`
  etc. — the `*_payload_total{type=...}` family covers router keys only.
- `rpkirtr_client` (NIST's RTR test tool) is broken in **both** the
  srx-server and router images: linked against `libreadline.so.8`, which the
  images don't ship. `rtr_query.py` is the replacement; it (or equivalent)
  belongs in `labkit.py`.
- Krill CLI rejects a repeated `-s` flag with a confusing error — scripts
  should pass exactly one server URI.
- QuaggaSRx's VTY has **no** `show srx`-style commands (enable-mode `list`
  confirms). SRx state on the router side is visible only through the
  extended columns of `show ip bgp`; deeper inspection happens on the SRx
  console.

## State after this phase

Lab **running**, clean: 0 ROAs in Krill, Routinator serving 4 router keys at
serial 2, both BGP sessions Established, received routes `SRxVal (-,v,-)`.
`rtr_query.py` lives in `lab/tools/`; fold it into `labkit.py` in Phase 5.

Next: Phase 3 — four-AS topology with point-to-point veth links, per-AS
configs, documented capture point per link; exit criterion is signature count
at AS64605 == hop count.
