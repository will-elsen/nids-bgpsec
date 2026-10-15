# Phase 1 — two-router smoke test: PASSED (2026-07-30)

Exit criterion from the plan: *a signed UPDATE validates as `Valid` end to end.*
Met, with the full RPKI chain live — details below.

## What broke on the first attempt (Jul 28), and the fixes

Both fixes are in `bgpsec-p1.clab.yml`; the upstream testbed is untouched.

1. **`nlnetlabs/krill:latest` moved to the 0.15+ CLI.** SIDN's `sign_csr.sh`
   invokes `krillc bgpsec add` with `-t/-c/-s` flags that 0.15 removed, so
   `krillc` crash-looped with `unexpected argument '-t'` and never signed a
   CSR. **Fix:** pin `nlnetlabs/krill:v0.14.5` (verified: its
   `krillc bgpsec add --help` matches the script). Routinator pinned to
   `v0.15.2` for the same reproducibility reason — its config keys
   (`enable-bgpsec`, `no-rir-tals`, `extra-tals-dir`) are all valid there.

2. **One-shots restarted forever, so the deploy hung.** The default restart
   policy restarts a container even after a clean exit, which means
   containerlab's `wait-for: {stage: exit}` never fires. This — not the CLI
   error itself — is why the Jul 28 deploy hung with an empty `rsync_ta/`.
   **Fix:** `restart-policy: "no"` on `krillc` and `tal_share`.

## Verification evidence

Chain, each link observed directly:

| Link | Evidence |
|---|---|
| krillc → Krill | `Exited (0)`; log: "Added certificate for AS6460{2..5}" (all four CSRs signed) |
| Krill → repo → Routinator | Routinator metrics: `router_keys` valid/contributed = **4** from the testbed TA |
| Routinator → RTR → SRx | srx_server log: RTR v1 session to 10.0.0.14:3323, `Received RPKI-RTR PDU[9]` (Router Key), "RPKI/Router Key Stored in srxcryptoapi" |
| SRx has no local keys | SRxCryptoAPI warns `Invalid directory "/var/lib/bgpsec-keys"` — validation keys can *only* have come over RTR |
| Router validation | `show ip bgp` on both routers: received prefix `SRxVal (-,v,-)` (path validation **Valid**), LocPrf 120 = the `valid → add 20` policy fired |
| Signatures on the wire | pcap on as64602 during a session reset: two `BGPsec_PATH` attrs (flags 0x90, type 33); each sender's SKI sits at attr start + 15 bytes, exactly RFC 8205's first signature-segment SKI position for a 1-hop path |

BGP state: as64602 ↔ as64603 Established, one prefix each way
(10.2.0.0/16 ← → 10.3.0.0/16). The `10.0.0.4` neighbor in
`quagga_as64603.conf` has no container in this topology and stays down by
design (upstream config is shared with the four-router setup).

## Operational notes

- Reset between runs: wipe `state/rsync_repo/*` and `state/rsync_ta/*`
  (root-owned — use `docker run --rm -v $PWD/state:/state alpine rm -rf ...`).
  `key_setup/testbed_keys` survives redeploys fine: `sign_csr.sh` re-signs the
  same CSRs and overwrites `.cert` files idempotently.
- No `vtysh` in the QuaggaSRx image. Drive bgpd via
  `docker exec <node> bash -c '(echo zebra; ...) | telnet localhost 2605'`.
  `labkit.py` should wrap this.
- **`tshark` is not installed on this host** — plan §5 assumed the Ubuntu
  package would be present. The notebook preflight must check for it (and
  `quick-setup.sh` should install it). The pcap-byte fallback used here works
  but is not the teaching experience we want.
- Capture works as designed: `docker exec <node> tcpdump -i eth0 -w ... port 179`
  with no sudo. In this flat topology BGP rides the mgmt bridge (`eth0`);
  per-link capture points arrive with Phase 3's veth links.

## Status

Lab left **running** (`containerlab destroy -t bgpsec-p1.clab.yml --cleanup`
to tear down). Next: Phase 2 is largely subsumed — this topology already runs
the full Krill → krillc → tal_share → Routinator → SRx chain with staged
ordering. Remaining Phase 2 work is only the routers' *own* RTR cache view
(the plan's "routers show a synced cache"), then Phase 3's four-AS topology
with point-to-point links.
