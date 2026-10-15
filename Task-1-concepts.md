[README](README.md) | [Introduction](Introduction.md) | [Datasets](Datasets.md) | [Containerlab](Containerlab.md) | [Tasks](Tasks.md) | Task 1 ⮕ | [Task 2](Task-2-bgpsec-lab.md) | [Notebook](nids-bgpsec.ipynb)

# Task 1 Guidance: BGPsec Concepts

This page provides implementation guidance for Task 1 of [nids-bgpsec.ipynb](nids-bgpsec.ipynb).

Task 1 has no lab work. Every answer comes from reasoning about the mechanism described in the [Introduction](Introduction.md), and the questions check that you can explain it in your own words before you see it run.

---

## Predicting the obstacles (Task 1.1)

Q1–Q5 ask you to predict, so answer them **before** reading *Task 1 Background: Why Deployment Is Hard*. A prediction that turns out wrong is fine; a prediction copied from that section is not a prediction.

For each angle, ask two questions: what does this operator **pay**, and what does this operator **get back**, today, with the internet as it is?

- **The first adopter (Q1).** Trace a route from its origin to you. Which ASes on that path must have deployed BGPsec for you to verify anything? What happens at the first one that has not? *BGPsec Path Validation* and *What BGPsec Does Not Do* describe what a router can and cannot check.
- **The unsigned majority (Q2).** You must keep accepting plain BGP. Put yourself in the attacker's position: given that rule, do you need to defeat the signatures at all?
- **The router's workload (Q3).** Count operations. *The BGPsec_PATH Attribute* says what each AS signs over. How many signatures does one update carry, how many does a full table need, and can one signature be reused for two neighbors?
- **The keys (Q4).** *Router Certificates and Keys* describes what must exist for a signature to verify. List what has to be created, published, renewed and revoked — then ask what a receiving network does with your routes on the day one of those steps is missed.
- **The comparison (Q5).** Both mechanisms are signed and both are rooted in the RPKI, so the difference is not the cryptography. Compare *who has to act* before anyone benefits.

---

## Answering the concept questions (Task 1.2)

| Question | Where the Introduction covers it |
| --- | --- |
| Q6 | *Router Certificates and Keys*, *The BGPsec_PATH Attribute* |
| Q7 | *The BGPsec_PATH Attribute*, the list of what each AS signs over |
| Q8 | *How BGPsec Stops AS_PATH Manipulation*, *How BGPsec Relates to Origin Validation* |
| Q9 | *What BGPsec Does Not Do* |
| Q10 | *What BGPsec Does Not Do*, *Task 1 Background: Why Deployment Is Hard* |

> **Gotcha:** Q7 and Q8 are easy to answer with "because the attacker doesn't have the key". That is true of every signature scheme. A full answer names *which* signature the attacker would need, *who* would have had to make it, and *which neighbor* it would have to name.

---

## What Your Write-Up Should Address

- **Q1** — what a lone adopter can verify today, and why.
- **Q2** — how an attacker exploits the obligation to accept unsigned routes.
- **Q3** — the per-update and per-table signing and verification cost, and its effect during convergence.
- **Q4** — the certificate and key lifecycle work, and the consequence of getting it wrong.
- **Q5** — the structural difference between origin validation and BGPsec that explains their deployment.
- **Q6** — what a router certificate binds, and what BGPsec_PATH adds to an AS_PATH.
- **Q7** — why the target ASN is signed, and the replay or splicing attack it prevents.
- **Q8** — the claim each validator checks, and where the forged path fails.
- **Q9** — BGPsec's verdict on a signed route leak, and why it is correct but unhelpful.
- **Q10** — why one non-BGPsec AS breaks protection downstream, and what that means for early adopters.

[README](README.md) | [Introduction](Introduction.md) | [Datasets](Datasets.md) | [Containerlab](Containerlab.md) | [Tasks](Tasks.md) | Task 1 ⮕ | [Task 2](Task-2-bgpsec-lab.md) | [Notebook](nids-bgpsec.ipynb)
