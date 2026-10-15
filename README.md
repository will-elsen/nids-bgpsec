README ⮕ | [Tasks](Tasks.md) | [BGPsec](bgpsec_understanding.md) | [Task 2](Task-bgpsec-lab.md) | [Lab Exercise](bgpsec_lab_exercise.ipynb)

### Network Infrastructure Data Science (NIDS) Module

---

# BGPsec — Signing the Whole Path

## Learning Objectives

The goal of this module is to:
- learn how BGPsec closes the path-validation gap that origin validation leaves open, with per-hop signature chains, and why its deployment has lagged so far behind origin validation
- run BGPsec for real — deploy a containerized six-AS internet with its own RPKI, watch signature chains grow hop by hop on the wire, defeat a path forgery, revoke a router certificate, and see first-hand why partial deployment yields so little

## Overview

This module assumes you know how BGP works and how RPKI route origin validation (ROV) checks who may originate a prefix. Start by reading **Understanding BGPsec**. Each file contains marked sections and questions for you to fill in as you go.

- step 1 [review the tasks index](Tasks.md) — the ordered list of tasks (1–2) in this module
- step 2 [read understanding BGPsec](bgpsec_understanding.md) — how signed paths stop AS_PATH forgery; fill in your deployment-obstacle predictions and answer the *Check your understanding* questions (Task 1)
- step 3 complete the [BGPsec lab exercise notebook](bgpsec_lab_exercise.ipynb) — drive a live BGPsec deployment in containerlab: verify a real signature chain against the RPKI, capture signatures accumulating on the wire, replay the path forgery against them, revoke a certificate, and break the chain with one unsigned AS (Task 2); read the [Task 2 guidance](Task-bgpsec-lab.md) first — it covers the GitHub Codespace this notebook runs in
- step 4 commit and push your completed module to github

### Directory Structure

```
bgpsec_module
├- Tasks.md                         # Index of every task in this module (Tasks 1-2)
├- bgpsec_understanding.md       ⬅  # BGPsec - signed AS_PATHs, and why deployment is hard
├- Task-bgpsec-lab.md               # Guidance - running the containerlab BGPsec lab (Task 2)
├- bgpsec_lab_exercise.ipynb     ⬅  # Notebook - drive a live BGPsec network: sign, verify, forge, revoke
├- .devcontainer/                   # Codespace setup - containerlab, lab images, Python, ready to run
└- containerlab/                    # The lab itself - topology, router configs, RPKI plane, tooling
```

### Glossary

- **Autonomous System (AS)**: A network under a single administrative control (an ISP, cloud provider, university), identified by a globally unique **AS number (ASN)**.
- **AS_PATH**: The ordered list of ASes a route has traversed. Each AS prepends its own ASN as it re-advertises the route; the rightmost ASN is the origin.
- **Origin AS**: The AS that originates a prefix announcement — the rightmost ASN in the AS_PATH, and the ASN that RPKI checks for authorization.
- **AS_PATH manipulation (path forgery)**: Advertising a partly or wholly fabricated AS_PATH — enabling stealthy interception (man-in-the-middle) rather than just blackholing.
- **RPKI (Resource Public Key Infrastructure)**: A cryptographic system layered alongside BGP that publishes verifiable, signed records of who is authorized to originate which prefixes.
- **ROA (Route Origin Authorization)**: The signed RPKI object declaring an origin ASN, a prefix, and a **Max Length** — the most specific announcement the origin is authorized to make.
- **ROV (Route Origin Validation)**: The check a router runs on every route's (prefix, origin ASN) pair against published ROAs, labeling it **Valid**, **Invalid**, or **Not Found** — with Invalid routes dropped.
- **BGPsec**: The extension that cryptographically protects the *entire AS_PATH*, closing the path-validation gap that RPKI/ROV leaves open.
- **Router certificate**: An RPKI certificate binding a public key to an ASN, so any router can verify that AS's BGPsec signatures.
- **BGPsec_PATH**: The attribute that replaces AS_PATH in BGPsec updates — the sequence of ASes plus a nested, forward-signed signature from each one, so the path cannot be altered or replayed.
- **Route leak**: A route propagated in violation of business policy (e.g. a customer re-announcing one provider's routes to another) — the signatures are genuine but the propagation is wrong, which is why BGPsec cannot catch it.
- **ASPA (Autonomous System Provider Authorization)**: A newer RPKI object in which an AS lists its authorized upstream providers, targeting route leaks — and, unlike BGPsec, deployable unilaterally.
- **SKI (Subject Key Identifier)**: A SHA-1 hash of a router's public key. Every BGPsec signature carries the SKI of the key that made it, so a verifier knows which router certificate to check it against.
- **Containerlab**: An open-source tool that deploys networks of containerized routers joined by virtual point-to-point links — the platform the BGPsec lab runs on.

README ⮕ | [Tasks](Tasks.md) | [BGPsec](bgpsec_understanding.md) | [Task 2](Task-bgpsec-lab.md) | [Lab Exercise](bgpsec_lab_exercise.ipynb)
