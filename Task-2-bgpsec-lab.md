[README](README.md) | [Introduction](Introduction.md) | [Datasets](Datasets.md) | [Containerlab](Containerlab.md) | [Tasks](Tasks.md) | [Task 1](Task-1-concepts.md) | Task 2 ⮕ | [Notebook](nids-bgpsec.ipynb)

# Task 2 Guidance: The BGPsec Lab

This page provides implementation guidance for Task 2 of [nids-bgpsec.ipynb](nids-bgpsec.ipynb).

Instead of analyzing datasets, you drive a **live network**: six BGP autonomous systems, each in its own container, with a complete self-signed RPKI (CA, publication point, validator) running alongside them. The routers genuinely speak BGPsec — they sign what they forward and verify what they receive — and you capture the signatures out of real BGP packets on the wire. The notebook drives the lab through `labkit` and asserts what it claims with checkpoint cells. Setup, timings, and the `labkit` reference are in the [Containerlab guide](Containerlab.md).

---

## Reading a route line

Most of what you reason about comes from `lab.show(node)`, which prints one line per path in this shape:

```
as64604: 1 path(s) to 10.64.2.0/24
  *> <AS path>              via <peer>      origin=<state> path=<state> lp=<local pref>  best
```

The fields are documented in [Datasets](Datasets.md#router-path-records). The two that matter most are the two validation axes: **origin** is route origin validation against the lab's ROA, and **path** is BGPsec path validation. Read them separately — they answer different questions, and in Task 2.4 they disagree.

---

## What to look for in each step

**Task 2.1.** You see the same SKI twice: once from the key vault on disk, once in a Router Key PDU from the validator. Match one by hand. The validator only serves a key after checking its certificate chain.

**Task 2.2.** After the switch, look at the route's `segments`, one (ASN, SKI) pair per signature. Compare each SKI with the vault from Task 2.1. That is the third place the same identity appears.

**Task 2.3.** Each link is captured separately, so you can see exactly what one AS hands to the next. Compare the number of AS hops on each link with the number of signatures.

**Task 2.4.** Before you run the forgery, predict both axes for the forged route. Then answer Q11 by applying plain BGP's best-path rules to the two paths, and Q12 by asking which AS would have had to sign what, naming which neighbor.

**Task 2.5.** Watch what does *not* happen when the certificate is revoked: whether any router is reconfigured, and whether any session resets. Note where the change was made and how it reached the routers.

**Task 2.6.** Compare the route's validation result and local preference (`lp`) with Task 2.2, and compare what the far-end observer AS64605 can still prove.

---

## Common pitfalls

> **Gotcha:** A route appears in the table a moment before the validator has answered for it. The notebook's `wait_for_route(..., settled=True)` calls handle this. If you explore by hand and see `undefined` validation states, you looked too early.

> **Gotcha:** Never restart lab containers with `docker restart`. The virtual wires do not survive it, and the failure is silent. The lab restarts daemons *inside* containers instead, and `lab.deploy()` recovers from anything.

> **Gotcha:** BGPsec rides on the RPKI. Without the ROA baseline from Task 0, the origin axis stays `notfound` and the later checkpoints fail. Run the notebook top to bottom.

> **Note:** `lab.capture(node, iface)` writes pcaps you can open in Wireshark, which has understood `BGPsec_PATH` since version 3.2.

---

## What Your Write-Up Should Address

- **Q11** — which of the two paths plain BGP would prefer, and the best-path rule that decides it.
- **Q12** — which signature the forged path is missing, who would have had to make it, and why AS64666 cannot.
- **Q13** — why each signature names its recipient, and what an AS could do if it did not.
- **Q14** — whether the two verdicts in Task 2.4 are both correct, and what claim each validator tested.
- **Q15** — who gained the power to remove routes, one way it is necessary, and one way it is a risk.
- **Q16** — the two strongest reasons for BGPsec's tiny real-world footprint, argued from what you observed, and why an attacker on a partially deployed internet needs no forged signatures.

[README](README.md) | [Introduction](Introduction.md) | [Datasets](Datasets.md) | [Containerlab](Containerlab.md) | [Tasks](Tasks.md) | [Task 1](Task-1-concepts.md) | Task 2 ⮕ | [Notebook](nids-bgpsec.ipynb)
