# Phase 3 — four ASes on point-to-point links: PASSED (2026-07-31)

Exit criterion from the plan: *signature count observed at AS64605 equals the
hop count.* Met, and observed as a **growth curve** across all three links
rather than only at the endpoint — 1 → 2 → 3 signatures. That progression is
the Part C teaching artifact, and it is only visible because each peering has
its own veth pair.

## Verification evidence

BGP state after a clean deploy: all three peerings Established, `10.64.2.0/24`
originated by AS64602 reaching AS64605 with `AS_PATH 64604 64603 64602`.

Signature growth, captured per link with `docker exec … tcpdump` (no sudo) and
dissected with `lab/tools/bgpsec_dissect.py`:

| Link | Capture point | Secure_Path | Sig segments | SKIs (in order) |
|---|---|---|---|---|
| 02→03 | `as64602:eth1` | AS64602 | **1** | `8BF7BA16…` |
| 03→04 | `as64603:eth2` | AS64603 AS64602 | **2** | `65DC493F…`, `8BF7BA16…` |
| 04→05 | `as64604:eth2` | AS64604 AS64603 AS64602 | **3** | `603CE9A6…`, `65DC493F…`, `8BF7BA16…` |

Every SKI matches `key_setup/testbed_keys/ski-list.txt` exactly
(64602=`8BF7BA16BAC2D49E1663657AABD3A0480F686A31`,
64603=`65DC493F029B0FDE1BDDC4B67B7DAF468D6054BF`,
64604=`603CE9A6618164E26A3FE32E8DAD129D5B9C0DE1`), and the segment order is
newest-signer-first per RFC 8205. Signatures are 71–72 bytes — DER-encoded
ECDSA P-256, as expected.

Receiver-side result at the observer:

```
     Network              Next Hop      AS_PATH              Attrs
,V*> 10.64.2.0/24         10.45.0.4     64604 64603 64602    [{Origin: i} {bgpsecs}]
```

and on the QuaggaSRx transit routers, `show ip bgp` reports `SRxVal (-,v,-)`
with LocPrf 120 — path validation **Valid**, the `valid → add 20` policy fired.

## Findings

- **GoBGP-SRx validates locally and does report state.** AS64605 never talks to
  `srx_server`; it verifies via srx-crypto-api against the shared key vault.
  Its status column is `<origin>,<bgpsec>` — the `,V` above means origin
  NotFound (no ROA at the time), BGPsec **Valid**. This resolves the Phase 3
  open question: the observer AS is a usable observation point.

- **A Docker restart silently breaks the lab.** Containerlab veths do not
  survive container recreation. Found this at the start of the phase: all eight
  containers were `Up`, but `eth1`/`eth2` were gone from every router, the
  `exec:` address adds were lost, and AS64605's session sat in `Active`. Nothing
  reports an error — the lab just looks deployed and does not work. **The
  notebook needs a preflight check for this** (assert `eth1` exists on
  `as64602`), because a student who reboots between sessions will hit it every
  time. Recovery is `destroy --cleanup` + `deploy`, not `docker start`.

- **Capture timing: reset the session adjacent to the capture point.** A
  `clear ip bgp *` on AS64602 cascades, but the re-announcement toward AS64605
  did not land inside a 30 s window on `as64604:eth2` — that capture came back
  empty. Clearing `10.45.0.5` on AS64604 directly produced the 3-signature
  UPDATE immediately. Exercise cells should reset the local session, not an
  upstream one.

- **Origin validation is off in these configs, by inheritance.** The upstream
  configs carry `srx evaluation bgpsec distributed`, so the origin column stays
  `-` even with a valid ROA in place. Confirmed the ROA does reach the router's
  validator — `srx_server` logged
  `ROA-wl: Ann [originAS: 64602, prefix: 10.64.2.0/24, max-len: 24]` and
  Routinator's `routinator_ta_valid_vrps_total` went 0 → 1 in ~25 s — so the
  gap is purely the router's evaluation setting. QuaggaSRx's VTY offers
  `srx evaluation origin | bgpsec | aspa`; `origin` is the knob Part B needs.
  **Not yet exercised** — that is Phase 4 work.

## State after this phase

Lab **running**. Captures kept in `phase3/captures/` (`l23`, `l34`, `l45b`).
The test ROA for `10.64.2.0/24 => 64602` was left in Krill by the last check —
remove it before Part A, which requires an unprotected baseline:

```
docker exec clab-bgpsec-p3-krill krillc roas update \
  --remove "10.64.2.0/24 => 64602" -t a_random_admin_token -c testbed \
  -s http://10.0.0.10:3000/
```

Next: Phase 4 — attacker AS64666 on `as64604:eth3`, then the Part A–D arc.
