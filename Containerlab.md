[README](README.md) | [Introduction](Introduction.md) | [Datasets](Datasets.md) | Containerlab ⮕ | [Tasks](Tasks.md) | [Task 1](Task-1-concepts.md) | [Task 2](Task-2-bgpsec-lab.md) | [Notebook](nids-bgpsec.ipynb)

# Containerlab and labkit Guide

This guide covers the two tools the lab is built on: **containerlab**, which runs the routers as containers joined by virtual links, and **labkit**, the small Python library the notebook uses to drive them. You will not need to type containerlab commands yourself — `labkit` runs them — but knowing what is underneath explains what the notebook's cells are doing and how to recover when something goes wrong.

---

## 1. What containerlab is

[Containerlab](https://containerlab.dev) deploys networks of containerized routers from a topology file. Each router is a Docker container, and each link between two routers is its own virtual point-to-point wire (a veth pair), so capturing on one link shows exactly what one AS hands to the next.

### 1.1 The lab's topology

```
AS64602 ──── AS64601 ──── AS64603 ──── AS64604 ──── AS64605
 origin       transit      transit      transit      observer
                                            │
                                        AS64666
                                        attacker
```

Alongside the six routers run the RPKI services described in [Datasets](Datasets.md): Krill, rsyncd, Routinator, and NIST's SRx-server validation engine, which five of the routers consult. The topology file is `containerlab/lab/phase4/bgpsec-p4.clab.yml`.

### 1.2 The four lab states

The lab has four configurations, which `lab.set_part()` switches between without recreating any container:

| Part | State |
| --- | --- |
| `a` | unprotected plain BGP: no validation (the state `lab.deploy()` starts in) |
| `b` | route origin validation only |
| `c` | full BGPsec: every router signs and verifies |
| `d` | partial deployment: the origin speaks plain BGP, everyone else BGPsec |

---

## 2. Running the lab in a GitHub Codespace

The lab needs Linux, Docker, and containerlab. The repository ships a devcontainer that provides all three in a GitHub Codespace, so you need only a browser.

### 2.1 Creating the Codespace

1. On the repository's GitHub page: **Code → Codespaces → Create codespace on main**. Pick a **4-core** machine if you are offered a choice.
2. The editor opens while setup continues in a terminal panel. The setup script installs the notebook's Python packages, loads the router images, and pre-pulls the RPKI images — a few minutes.
3. Wait for the terminal to print `=== done — open nids-bgpsec.ipynb and run it from the top ===`.
4. Open `nids-bgpsec.ipynb`, select the **Python 3** kernel when asked, and run it from the top.

> **Gotcha:** Opening the notebook before setup finishes is the classic mistake: cells fail with missing images that were still loading. Wait for the `done` line.

### 2.2 When setup fails partway

A network hiccup during the image download is the usual cause. Open a terminal and re-run the setup script — it is safe to repeat and picks up whatever is missing:

```bash
bash .devcontainer/postCreate.sh
```

If the image download fails entirely, the script builds the images from source instead; that also works, it just takes about 20 minutes.

### 2.3 The stop-and-resume rule

> **Gotcha:** If your Codespace was **stopped and resumed** — closing the tab for a while is enough, because idle Codespaces stop automatically — the containers come back up but the virtual wires between them do not. Everything shows green and nothing reports an error, but no routes move. The fix is always the same: re-run the `lab.deploy()` cell. It tears down whatever half-state exists and rebuilds cleanly in 2–3 minutes.

### 2.4 Quota

GitHub's free tier includes 120 core-hours a month, so a 4-core machine gives you roughly 30 hours of lab time. Stop the Codespace when you are done (**Codespaces → Stop**) rather than leaving it idle.

---

## 3. labkit: the notebook's driving library

The notebook imports it once — `import labkit as lab` — and every cell goes through it. Its helpers **poll rather than sleep**: a cell that seems to hang is usually waiting for BGP to converge, and returns the moment it has.

### 3.1 Setup and teardown

| Call | What it does |
| --- | --- |
| `lab.preflight()` | checks the machine can host the lab and names anything to fix |
| `lab.deploy()` | builds the lab from scratch in Part `a`; safe to re-run, and the full reset |
| `lab.status()` | one screen: every BGP session, the RPKI counts, and the best path at AS64604 and AS64605 |
| `lab.reset()` | back to the starting state: Part `a`, no attack, no ROA |
| `lab.destroy()` | tears the containers down entirely |

### 3.2 Reading routes

| Call | What it does |
| --- | --- |
| `lab.routes(node)` | every path `node` holds for the lab prefix, as `Route` records |
| `lab.best(node)` | the path `node` is using, or `None` |
| `lab.show(node)` | prints those paths one per line |

The `Route` fields are documented in [Datasets](Datasets.md#router-path-records). Useful constants: `lab.PREFIX` (`10.64.2.0/24`), `lab.VICTIM` (`as64604`), `lab.OBSERVER` (`as64605`), `lab.ATTACKER_PEER` (the attacker's address as AS64604 sees it).

### 3.3 Changing the lab

| Call | What it does |
| --- | --- |
| `lab.set_part(p)` | switches to lab state `a`–`d` (section 1.2) by restarting each routing daemon in place |
| `lab.add_roa()` | issues the ROA authorizing AS64602 to originate the prefix, and waits for the validator |
| `lab.attack("forge")` | AS64666 announces the prefix with the forged path `64666 64602` |
| `lab.attack("stop")` | AS64666 withdraws everything |
| `lab.revoke_router_key(asn)` | removes that AS's router certificate at the CA and waits for the validator to drop it |
| `lab.restore_router_key(asn)` | re-issues it |

### 3.4 Waiting for the network

| Call | Returns when |
| --- | --- |
| `lab.wait_for_best(node, as_path=...)` | `node`'s best path matches |
| `lab.wait_for_route(node, via=..., settled=True)` | a matching path exists — best or not — and, with `settled`, has been validated |
| `lab.wait_for_gone(node, via=...)` | the path from that peer has been withdrawn |

### 3.5 Keys and packets

| Call | What it does |
| --- | --- |
| `lab.skis()` | `{ASN: SKI}` from the lab's key vault on disk |
| `lab.rtr_dump()` | everything the validator serves a router over RTR, one PDU per line |
| `lab.vrp_count()`, `lab.router_key_count()` | counts of VRPs and router keys served over RTR |
| `lab.capture(node, iface)` | captures BGP on one link and returns the pcap path |
| `lab.dissect(pcap)` | the `BGPsec_PATH` attributes in a pcap |
| `lab.signature_growth()` | captures all four links and counts hops and signatures on each |

### 3.6 Assertions

`lab.check(claim, ok, detail)` prints one `[PASS]` or `[FAIL]` line naming what it verified, and `lab.checkpoint(name)` summarizes the checks since the last checkpoint. A checkpoint with a failure tells you to fix it before moving on: later steps build on earlier ones.

---

## 4. Timings

| Cell | Time | What it is doing |
| --- | --- | --- |
| `lab.deploy()` | 2–3 min | the containers plus building the RPKI trust chain from nothing |
| `lab.set_part(...)` | about 1 min | restarting routing daemons — BGPsec only takes effect at daemon start |
| `lab.signature_growth()` | about 2–3 min | four packet captures, each with a BGP session reset |

The whole notebook takes 45–60 minutes, most of it reading and answering.

---

## 5. Troubleshooting

> **Gotcha:** **Nothing moves after a break.** Your Codespace was stopped and resumed (section 2.3). Re-run `lab.deploy()`.

> **Gotcha:** **`undefined` validation states.** You looked at a route before the validator answered for it. Use the `wait_for_*` helpers, or re-run the observation cell a few seconds later.

> **Gotcha:** **Never use `docker restart` on a lab container.** The virtual wires do not survive it and the failure is silent. `lab.deploy()` recovers from it.

> **Gotcha:** **A step ran out of order.** Every observation cell is safe to re-run. If the lab is in a state you cannot explain, `lab.status()` shows every session and route on one screen, and `lab.deploy()` followed by the notebook from the top is the full reset.

---

## 6. Going further

`lab.capture(node, iface)` writes pcaps under `containerlab/lab/phase4/captures/`. Download one from the Codespace's file explorer and open it in [Wireshark](https://www.wireshark.org), which has dissected `BGPsec_PATH` since version 3.2, to see the Secure_Path and Signature_Block field by field.

[README](README.md) | [Introduction](Introduction.md) | [Datasets](Datasets.md) | Containerlab ⮕ | [Tasks](Tasks.md) | [Task 1](Task-1-concepts.md) | [Task 2](Task-2-bgpsec-lab.md) | [Notebook](nids-bgpsec.ipynb)
