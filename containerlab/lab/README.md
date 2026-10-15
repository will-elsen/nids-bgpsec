# BGPsec teaching lab

A Containerlab lab that walks students through hijacking a prefix, defending
against it with RPKI, defeating that defence, deploying BGPsec, and then
seeing why almost nobody has.

**The deliverable is `bgpsec-lab.ipynb`.** Everything else here exists to make
that notebook work.

## Running it

```bash
docker load < dist/bgpsec-lab-images.tar.gz     # once
jupyter lab bgpsec-lab.ipynb                     # then run top to bottom
```

The notebook's first cell checks the host and names the specific fix for
anything missing. No step in the lab needs `sudo`: containerlab is installed
setuid, students are in the `docker` group, and packet capture runs inside the
router containers.

About 60–75 minutes end to end.

## What is here

| Path | |
|---|---|
| `bgpsec-lab.ipynb` | the lab students run |
| `bgpsec-lab-instructor.ipynb` | same, plus model answers and teaching notes |
| `labkit.py` | everything the notebook calls — deploy, drive, inspect, assert |
| `reset.sh` | put the lab back to a clean state without a redeploy |
| `phase4/` | the topology, the per-part configs, and the key vault |
| `router_keys/` | the lab's own router private keys (AS64601, AS64666); `tools/build_vault.sh` builds the vault from these plus the vendored testbed's four |
| `phase1/`, `phase3/` | earlier phases' topologies and their verification records |
| `tools/` | config generation, capture dissection, RTR client, test harnesses |
| `overlay/` | thin Dockerfiles over the upstream images |
| `dist/` | the distributable image bundle |

Both notebooks are generated: edit `tools/build_notebook.py`, then

```bash
python3 tools/build_notebook.py
```

Editing the `.ipynb` directly means the student and instructor copies drift,
and a stale instructor copy is worse than none.

## The topology

```
AS64602 ──── AS64601 ──── AS64603 ──── AS64604 ──── AS64605
 origin       transit      transit      transit      observer
 QuaggaSRx    QuaggaSRx    QuaggaSRx    QuaggaSRx    GoBGP-SRx
                                            │
                                        AS64666
                                        attacker
```

Plus an RPKI plane on the management network: Krill (CA), rsyncd (publication
point), Routinator (validator), and SRx-server (NIST's validation engine,
which the QuaggaSRx routers delegate to).

Each inter-AS link is a dedicated veth pair, which is what makes the signature
growth in Part C observable one hop at a time.

Containerlab will draw it from the topology file, in
`phase4/clab-bgpsec-p4/graph/`:

```bash
containerlab graph -t phase4/bgpsec-p4.clab.yml --mermaid   # or --dot
```

## The four states

The same routers run four configurations, generated from one table in
`tools/gen_configs.py`:

| | origin validation | BGPsec |
|---|---|---|
| **a** | off | off |
| **b** | on, drops invalid | off |
| **c** | on | on, drops invalid |
| **d** | on | on, except AS64602 |

`labkit.set_part()` swaps configs and restarts each daemon in place. RPKI state
survives the switch, so a ROA issued in Part B is still there in Part C.

## Checking it still works

```bash
python3 tools/smoke_test.py              # drives all four parts, asserts on each
python3 tools/run_notebook.py bgpsec-lab.ipynb   # runs the notebook as a kernel would
```

The smoke test takes about ten minutes and is the fastest way to tell whether
a change broke an exercise. Run it after touching `gen_configs.py`, `labkit.py`,
or anything in `overlay/`.

## Notes for anyone maintaining this

- **Never `docker restart` a node.** Containerlab's veths do not survive
  container recreation: the node comes back with only `eth0`, and the lab
  looks deployed while being silently broken. The images run a supervisor as
  PID 1 so daemons can be restarted in place instead.
- **The images are not upstream.** `:local` adds tcpdump and that supervisor
  over `:upstream`. Rebuild with `./build-images.sh`.
- **Findings from building this** — including several QuaggaSRx and SRx-server
  behaviours that constrain what the curriculum can do — are written up in
  `phase3/PHASE3.md`, `phase4/PHASE4.md` and `PHASE5.md`. Read those before
  concluding something is a bug.
