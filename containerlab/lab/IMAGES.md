# Image provenance

Built by `lab/build-images.sh`, x86_64. Base images built 2026-07-28; the
`:local` overlays rebuilt 2026-07-31 to add the daemon supervisor (see below).

## Sources

| Source | Commit | Notes |
|---|---|---|
| [SIDN/bgpsec-testbed](https://github.com/SIDN/bgpsec-testbed) | `c90b222f15386a26e79976da6b826c22872d9679` | Vendored clone, unmodified |
| [usnistgov/NIST-BGP-SRx](https://github.com/usnistgov/NIST-BGP-SRx) | `e978750b7be3b51a2042517dd6c0568f56e4e03c` | HEAD at build time — **not pinned in the Dockerfiles** |
| [usnistgov/gobgpsrx](https://github.com/usnistgov/gobgpsrx) | `0c5bd49ac7bd8243e50d5db6b5923ba4bac1e90c` | HEAD at build time — **not pinned in the Dockerfiles** |

The upstream Dockerfiles `git clone` NIST sources without a ref, so a rebuild
picks up whatever is on master that day. The SHAs above are what went into the
current tarball. To make rebuilds reproducible, add `git checkout <sha>` after
the clone in each Dockerfile.

## Images

| Tag | Size | Contents |
|---|---|---|
| `bgpsec/quaggasrx:local` | 244 MB | QuaggaSRx 0.6.0.4 + srx-crypto-api, + `tcpdump`, + supervisor |
| `bgpsec/gobgpsrx:local` | 262 MB | GoBGP-SRx 2.14.0 + srx-crypto-api, + `tcpdump`, + supervisor |
| `bgpsec/srx-server:local` | 215 MB | SRx-Server 0.6.2.1, + supervisor |
| `bgpsec/tal-share:local` | 18.9 MB | Alpine + `get_ta.sh` |

`:upstream` tags are the pristine SIDN builds. `:local` adds two things via
`lab/overlay/*.Dockerfile`, and the lab only ever runs `:local`.

**Capture tooling** — `tcpdump`, `iproute2`, `iputils-ping`, `procps` — so
students capture with `docker exec <node> tcpdump` rather than
`ip netns exec`, which would need `sudo` and would hang a notebook cell on an
invisible password prompt.

**A supervisor as PID 1** (`overlay/run-daemon.sh`), so a daemon can be
restarted against an edited config *without recreating the container*. This is
not a convenience:

- BGPsec cannot be switched on or off on a live session — QuaggaSRx keeps
  emitting BGPsec-shaped UPDATEs to a peer that no longer negotiated the
  capability, and the session sits in Idle. The curriculum has to switch it
  four times, so daemons must restart.
- `docker restart` would do that, but containerlab's veth pairs do not survive
  container recreation. The node comes back with only `eth0`, no error is
  reported anywhere, and the lab looks deployed while being completely broken.
- `srx_server` needs it too, for a different reason: its client table is keyed
  by proxy ID and outlives the routers that registered. A router restarting
  into its own stale entry never completes the SRx handshake, so every
  validation returns `undefined` and the router drops the route. `set_part.sh`
  restarts the validation engine first, giving routers a clean table.

## Distributable

`lab/dist/bgpsec-lab-images.tar.gz` — 275 MB, the four `:local` images.
Regenerated 2026-07-31 to include the daemon supervisor; an older bundle will
deploy and then fail at the first part switch.

```
sha256  a4aca79dd28be59e805d2b1232892be62516bfad08ad9b7ddd44533bbeb23fb3   (2026-07-31 build)
sha256  7fe312e2cdde52f7d11e66e93e50e37c2bdf7cdcfd315259baa236b46d89ceb8   (2026-08-13 re-save, the `lab-images` release)
```

The 2026-08-13 re-save holds the same four image IDs as the 2026-07-31 build;
only the tarball bytes differ.

Load with `docker load < bgpsec-lab-images.tar.gz`.

The tarball (attached to the repo's `lab-images` release) is currently the
only hosted distribution. `tools/publish_images.sh` creates or refreshes that
release. `GHCR.md` is the runbook for publishing these
images to GitHub Container Registry instead.

Not included: `nlnetlabs/krill:v0.14.5`, `nlnetlabs/routinator:v0.15.2`,
`vimagick/rsyncd`. These pull from Docker Hub. The krill pin is **required**,
not cosmetic: `latest` (0.15+) removed the `-t/-c/-s` krillc flags that the
testbed's `sign_csr.sh` uses, which broke the first Phase 1 deploy — see
`lab/phase1/PHASE1.md`.

## Verified at build time

- `tcpdump 4.99.4` runs in both router images.
- `bgpd` resolves `libSRxProxy.so.6` and `libSRxCryptoAPI.so.3` — BGPsec support
  is compiled in and dynamically resolvable, not silently omitted.
