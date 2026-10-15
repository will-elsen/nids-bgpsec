[README](README.md) | [Tasks](Tasks.md) | [BGPsec](bgpsec_understanding.md) | Task 2 ⮕ | [Lab Exercise](bgpsec_lab_exercise.ipynb)

# Task 2 Guidance: The BGPsec Lab

This page prepares you to run [bgpsec_lab_exercise.ipynb](bgpsec_lab_exercise.ipynb).
It is a hands-on exercise: instead of analyzing
datasets, you drive a **live network** — six BGP autonomous systems, each in its own
container, with a complete self-signed RPKI (CA, publication point, validator)
running alongside them. The routers genuinely speak BGPsec: they sign what they
forward, verify what they receive, and you will capture the signatures out of real
BGP packets on the wire.

Everything lives under [`containerlab/`](containerlab/REFERENCE.md) and is driven
from the notebook through a small Python library (`labkit`). You do not edit router
configs or type into router consoles unless you want to; the notebook drives the
lab and asserts what it claims with checkpoint cells.

## Running it in a GitHub Codespace (recommended)

The repo ships a devcontainer that installs everything, so the setup is:

1. On the repo's GitHub page: **Code → Codespaces → Create codespace on main**.
   Pick a **4-core machine** if you are offered a choice.
2. Wait for setup to finish. The container build plus image loading takes a few
   minutes; the `postCreate` step prints what it is doing. (If you open the
   notebook before it finishes, cells will fail with missing images — wait it out.)
3. Open `bgpsec_lab_exercise.ipynb`, select the **Python 3** kernel when VS Code
   asks, and run it from the top.

If the setup step fails partway (a network hiccup during the ~260 MB image
download is the usual cause), open a terminal and re-run
`bash .devcontainer/postCreate.sh` — it is safe to repeat and picks up whatever
is missing. A fuller from-scratch runbook — verification steps, failure modes,
and the desktop/local alternatives — is in
[`containerlab/CODESPACES.md`](containerlab/CODESPACES.md).

**The one rule of Codespaces:** if your Codespace was **stopped and resumed**
(closing the tab for a while is enough — idle Codespaces stop automatically), the
containers come back up but the virtual wires between them do not. Everything shows
green and nothing reports an error, but no routes will move. The fix is always the
same: re-run the `lab.deploy()` cell. It tears down whatever half-state exists and
rebuilds cleanly in 2–3 minutes.

On quota: GitHub's free tier includes 120 core-hours/month, so a 4-core machine
gives you roughly 30 hours of lab time. Stop the Codespace when you are done
(**Codespaces → Stop**) rather than leaving it idle.

## Running it locally instead

The lab needs Linux (or WSL2) with Docker and [containerlab](https://containerlab.dev)
— `containerlab/quick-setup.sh` installs both on a fresh machine. Then either load
the prebuilt images (attached to this repo's `lab-images` release):

```bash
gh release download lab-images --pattern bgpsec-lab-images.tar.gz --dir containerlab/lab/dist
docker load < containerlab/lab/dist/bgpsec-lab-images.tar.gz
```

or build them from the vendored source (~20 minutes): `cd containerlab/lab &&
./build-images.sh`. After that the notebook works exactly as in a Codespace; its
first cell (`lab.preflight()`) checks the machine and names anything missing.

## What to expect while it runs

The notebook's helpers **poll rather than sleep**: a cell that appears to hang for
a minute is usually waiting for BGP to converge, and will return the moment it
has. Expect these to be slow, and let them finish:

| Cell | Time | What it is doing |
| --- | --- | --- |
| `lab.deploy()` | 2–3 min | 12 containers + building the RPKI trust chain from nothing |
| `lab.set_part(...)` | ~1 min | restarting routing daemons — BGPsec only takes effect at daemon start |
| `lab.signature_growth()` | ~2 min | four packet captures, each with a BGP session reset |

Every observation cell is safe to re-run. If you run something out of order and the
lab ends up in a state you cannot explain, `lab.status()` shows every session and
route on one screen, and `lab.deploy()` is the full reset.

## Common pitfalls

- **Judging a route before it settles.** A route appears in the table a moment
  before the validator has answered for it. The notebook's `wait_for_route(...,
  settled=True)` calls handle this — if you explore by hand and see `undefined`
  validation states, you looked too early.
- **Restarting lab containers with `docker restart`.** Never do this: the virtual
  wires do not survive it, and the failure is silent (see the Codespace rule
  above — it is the same failure). The lab restarts daemons *inside* containers
  instead, and `lab.deploy()` recovers from anything.
- **Skipping the ROA cell.** BGPsec rides on the RPKI: without the ROA baseline
  from cell 2.0, the origin axis stays `notfound` and the later assertions fail.
  Run the notebook top to bottom.

## Where to dig deeper

[`containerlab/REFERENCE.md`](containerlab/REFERENCE.md) is the complete walkthrough
of how the lab is built — topology, the two validation paths, every design decision.
`lab.capture(node, iface)` writes pcaps you can open in Wireshark, which has
understood `BGPsec_PATH` since version 3.2.

[README](README.md) | [Tasks](Tasks.md) | [BGPsec](bgpsec_understanding.md) | Task 2 ⮕ | [Lab Exercise](bgpsec_lab_exercise.ipynb)
