[README](README.md) | Tasks ⮕ | [BGPsec](bgpsec_understanding.md) | [Task 2](Task-bgpsec-lab.md) | [Lab Exercise](bgpsec_lab_exercise.ipynb)

# Tasks

Complete the tasks below in order.

The lab task has a guidance page — [Task 2](Task-bgpsec-lab.md) — covering setup,
timings, and common pitfalls. Read it before starting the notebook.

### Setting up for the lab notebook

The BGPsec lab notebook (Task 2) requires a running containerlab simulation, which runs
BGPsec live. You will run this on GitHub Codespaces; the repo's devcontainer installs
everything it needs.


## Task 1: Read Understanding BGPsec

Detailed Guidance → [Task 1](bgpsec_understanding.md)

Completed in [bgpsec_understanding.md](bgpsec_understanding.md). Learn how per-hop
signature chains close the path-validation gap that ROV leaves open, and why deployment
has lagged.

- [ ] Fill in the obstacle-prediction table: what you think goes wrong for the first
      adopter, the unsigned majority, the router's workload, and key management
- [ ] Answer the five *Check your understanding* questions

## Task 2: Run BGPsec on a Live Network

Detailed Guidance → [Task 2](Task-bgpsec-lab.md)

Completed in [bgpsec_lab_exercise.ipynb](bgpsec_lab_exercise.ipynb). The guidance page
also covers the GitHub Codespace setup this notebook runs in.

Task 1 treated BGPsec as description. Here you run it: six containerized BGP routers
with a complete self-signed RPKI, signing and verifying real announcements. The notebook
is fully scaffolded — there is no code to implement; the deliverables are the checkpoint cells passing and your reflection
answers.

- [ ] 2.0–2.2: lab deployed, ROA issued, BGPsec on — the real route validates on
      both axes, and every signature's SKI matches the router key the RPKI publishes
- [ ] 2.3: signature growth captured on the wire — 1, 2, 3, 4 signatures on the four
      successive inter-AS links
- [ ] 2.4: the path forgery arrives rated origin-**valid** but path-**invalid**, and
      is dropped
- [ ] 2.5: revoking AS64602's router certificate removes the route with no router
      touched; restoring it brings the route back
- [ ] 2.6: partial deployment — the unsigned origin breaks the chain, and policy
      falls back from dropping to de-preferring
- [ ] Reflection question 1: why each signature names its recipient, and what breaks
      without that
- [ ] Reflection question 2: the two verdicts in 2.4 — what claim each validator
      tested, and what a ROA can and cannot say
- [ ] Reflection question 3: where revocation power sits — necessity, risk, and what
      the lab's single-CA design has to do with it
- [ ] Reflection question 4: the deployment gap, argued from 2.6 and the real-world
      router-certificate counts — including why an attacker needs no forged signatures

[README](README.md) | Tasks ⮕ | [BGPsec](bgpsec_understanding.md) | [Task 2](Task-bgpsec-lab.md) | [Lab Exercise](bgpsec_lab_exercise.ipynb)
