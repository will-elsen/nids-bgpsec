README ⮕ | [Introduction](Introduction.md) | [Datasets](Datasets.md) | [Containerlab](Containerlab.md) | [Tasks](Tasks.md) | [Task 1](Task-1-concepts.md) | [Task 2](Task-2-bgpsec-lab.md) | [Notebook](nids-bgpsec.ipynb)

### [Network Infrastructure Data Science (NIDS) Assignment]

---

# BGPsec: Signing the Whole Path

**GitHub:** https://github.com/CAIDA/nids-bgpsec

## Authors

Will Elsen

## Learning Objectives

This assignment introduces BGPsec, the extension that protects the entire AS_PATH of a BGP route with a chain of per-hop signatures, and explains why its deployment has lagged so far behind route origin validation. You will run BGPsec for real: you will learn containerlab, which runs a network of containerized routers joined by virtual links, and labkit, the Python library that drives this lab. You will deploy a six-AS internet with its own RPKI, watch signature chains grow hop by hop on the wire, defeat a path forgery, revoke a router certificate, and see first-hand why partial deployment yields so little. Afterwards you will be able to explain what a BGPsec signature commits to, why a forged path fails validation while still passing origin validation, and why BGPsec has barely deployed.

## Overview

Start by reading **Introduction** to get the conceptual background. **Datasets** describes the lab data the notebook reads, and the **Containerlab** guide explains the lab environment and the library that drives it.

- step 1 [read the introduction](Introduction.md)
- step 2 [read dataset overviews](Datasets.md)
- step 3 [read the Containerlab guide](Containerlab.md)
- step 4 [review the tasks](Tasks.md)
- step 5 open this repository in a GitHub Codespace and complete nids-bgpsec.ipynb
  - Detailed setup instructions: [Containerlab guide, section 2](Containerlab.md#2-running-the-lab-in-a-github-codespace)
  - run every cell in order; each step ends in a checkpoint that must pass
  - answer all questions
- step 6 download your working notebook and replace ⬅ deliverable
- step 7 commit and push to github

### Directory Structure

```text
nids-bgpsec
├- Introduction.md                  # Introduction and background
├- Datasets.md                      # The lab-generated data the notebook reads
├- Containerlab.md                  # Containerlab, the Codespace, and the labkit library
├- Tasks.md                         # Task checklist and instructions
├- Task-1-concepts.md               # Guidance for Task 1
├- Task-2-bgpsec-lab.md             # Guidance for Task 2
├- .devcontainer/                   # Codespace setup - containerlab, router images, Python
├- containerlab/                    # The lab - topology, router configs, RPKI plane, labkit
├- nids-bgpsec.ipynb             ⬅  # Complete / Commit / Push
```

### Glossary

- **AS (Autonomous System)**: A network under a single administrative control, such as an ISP, cloud provider, or university, identified by a globally unique AS number (ASN).
- **AS_PATH**: The ordered list of ASes a route has traversed. Each AS prepends its own ASN as it re-advertises the route; the rightmost ASN is the origin.
- **AS_PATH manipulation (path forgery)**: Advertising a partly or wholly fabricated AS_PATH, enabling interception rather than just blackholing.
- **ASPA (Autonomous System Provider Authorization)**: An RPKI object in which an AS lists its authorized upstream providers, targeting route leaks; unlike BGPsec, it is deployable unilaterally.
- **BGP (Border Gateway Protocol)**: The path-vector routing protocol that exchanges reachability information between independently operated networks [ [RFC 4271](https://www.rfc-editor.org/rfc/rfc4271.html) ].
- **BGPsec**: The BGP extension that protects the entire AS_PATH with a signature from every AS that propagates the route [ [RFC 8205](https://www.rfc-editor.org/rfc/rfc8205.html) ].
- **BGPsec_PATH**: The attribute that replaces AS_PATH in BGPsec updates: the Secure_Path of ASes plus a Signature_Block holding one nested, forward-signed signature from each.
- **CA (Certificate Authority)**: The party that issues and revokes certificates; in the lab, Krill.
- **Codespace**: A cloud development environment hosted by GitHub, built from the repository's devcontainer [ [GitHub Codespaces](https://docs.github.com/en/codespaces) ].
- **Containerlab**: An open-source tool that deploys networks of containerized routers joined by virtual point-to-point links [ [containerlab.dev](https://containerlab.dev) ].
- **Krill**: NLnet Labs' RPKI certificate authority software, which issues the lab's ROA and router certificates [ [Krill](https://krill.docs.nlnetlabs.nl) ].
- **labkit**: The Python library in `containerlab/lab/labkit.py` that the notebook uses to drive and inspect the lab.
- **Local preference**: A BGP attribute an AS sets on received routes to rank them; higher wins, and it is checked before AS_PATH length.
- **Origin AS**: The AS that originates a prefix announcement: the rightmost ASN in the AS_PATH, and the ASN that origin validation checks.
- **pcap**: The packet-capture file format written by tcpdump and read by Wireshark.
- **Prefix**: A block of IP addresses, such as `10.64.2.0/24`, announced into BGP by the AS that can reach it.
- **ROA (Route Origin Authorization)**: The signed RPKI object declaring which AS may originate a prefix, and the most specific prefix length it may announce.
- **Route leak**: A route propagated in violation of business policy; the signatures are genuine but the propagation is wrong, which is why BGPsec cannot catch it.
- **Router certificate**: An RPKI certificate binding a public key to an ASN, so any router can verify that AS's BGPsec signatures [ [RFC 8209](https://www.rfc-editor.org/rfc/rfc8209.html) ].
- **Routinator**: NLnet Labs' RPKI validator, which checks the lab's certificates and serves the results to routers over RTR [ [Routinator](https://routinator.docs.nlnetlabs.nl) ].
- **ROV (Route Origin Validation)**: The check of a route's (prefix, origin ASN) pair against published ROAs, labeling it valid, invalid, or not found.
- **RPKI (Resource Public Key Infrastructure)**: The certificate hierarchy that publishes verifiable records of who holds which IP addresses and ASNs, underpinning both ROV and BGPsec.
- **RTR (RPKI-to-Router protocol)**: The protocol a validator uses to deliver validated ROA payloads and router keys to routers [ [RFC 8210](https://www.rfc-editor.org/rfc/rfc8210.html) ].
- **SKI (Subject Key Identifier)**: A SHA-1 hash of a router's public key. Every BGPsec signature carries the SKI of the key that made it, so a verifier knows which router certificate to check it against.
- **SRx (BGP Secure Routing Extension)**: NIST's BGPsec and origin-validation implementation; the lab's routers are QuaggaSRx and GoBGP-SRx, and SRx-server performs their validation.
- **VRP (Validated ROA Payload)**: A ROA after the validator has checked its signatures: a plain (prefix, max length, origin ASN) tuple that routers compare routes against.

README ⮕ | [Introduction](Introduction.md) | [Datasets](Datasets.md) | [Containerlab](Containerlab.md) | [Tasks](Tasks.md) | [Task 1](Task-1-concepts.md) | [Task 2](Task-2-bgpsec-lab.md) | [Notebook](nids-bgpsec.ipynb)
