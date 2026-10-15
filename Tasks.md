[README](README.md) | [Introduction](Introduction.md) | [Datasets](Datasets.md) | [Containerlab](Containerlab.md) | Tasks ⮕ | [Task 1](Task-1-concepts.md) | [Task 2](Task-2-bgpsec-lab.md) | [Notebook](nids-bgpsec.ipynb)

# Tasks

Complete the tasks below in order. All tasks are performed inside [nids-bgpsec.ipynb](nids-bgpsec.ipynb) — run the provided cells in order and answer the questions in the markdown cells that follow them. This notebook has no `# YOUR CODE HERE` sections: the lab is driven by provided code, and your deliverables are the passing checkpoint cells and your answers.

---

## Task 0: Setup and Lab Access

The lab runs in a **GitHub Codespace**, not on NRP's JupyterHub, because it needs Docker and containerlab, which the Codespace provides. [Containerlab guide, section 2](Containerlab.md#2-running-the-lab-in-a-github-codespace) walks through every step.

- step 1. Open this repository on GitHub and create a Codespace: **Code → Codespaces → Create codespace on main**, choosing a **4-core** machine if offered
- step 2. Wait for the setup script in the terminal to print `=== done — open nids-bgpsec.ipynb and run it from the top ===`
- step 3. Open `nids-bgpsec.ipynb`, select the **Python 3** kernel, and run the Task 0 cells
- [ ] `lab.preflight()` prints `Preflight passed — you can deploy.`
- [ ] `lab.deploy()` reports all sessions Established and the prefix reaching the far end
- [ ] `lab.status()` shows 1 VRP and 6 router keys served over RTR

---

## Task 1: BGPsec Concepts

Detailed guidance: [Task 1 — BGPsec Concepts](Task-1-concepts.md)

### Task 1.1 — Predict the deployment obstacles

Answer these **before** reading the Introduction's section *Task 1 Background: Why Deployment Is Hard*. Think through what actually changes for a network operator who turns BGPsec on tomorrow.

- [ ] **Q1** The first adopter. You enable BGPsec and none of your neighbors have. What protection do you actually gain today?
- [ ] **Q2** The unsigned majority. Most of the internet still sends plain BGP updates that you *must* keep accepting. What does an attacker do with that fact?
- [ ] **Q3** The router's workload. A plain BGP update carries an AS_PATH that is a few bytes to copy; a BGPsec update carries one signature per AS hop. What has to happen on a router holding a full internet routing table — roughly a million prefixes — and what happens during a convergence storm?
- [ ] **Q4** The keys. Signing requires private keys on (or behind) every border router in your network, and certificates that other networks fetch to verify you. What ongoing work does that create, and what breaks when it goes wrong?
- [ ] **Q5** Origin validation and BGPsec are both signed, RPKI-rooted mechanisms. What is different about BGPsec that made one of them easy to deploy and the other one hard?

### Task 1.2 — Check your understanding

Answer from the [Introduction](Introduction.md).

- [ ] **Q6** In one sentence each, what does a router certificate bind together, and what does the BGPsec_PATH attribute carry beyond an ordinary AS_PATH?
- [ ] **Q7** Why does each AS sign over the ASN it is sending the route to? What attack would be possible if it signed only over the prefix and its own ASN?
- [ ] **Q8** An attacker announces a prefix with a forged path ending in the real owner's ASN. Explain why this passes origin validation but fails BGPsec path validation.
- [ ] **Q9** A route leak is propagated by ASes that all sign correctly. What does BGPsec report, and why is that answer both correct and unhelpful?
- [ ] **Q10** Why does a single non-BGPsec AS in the middle of a path undo the protection for everyone downstream — and why does that make early adoption unattractive?

---

## Task 2: Run BGPsec on a Live Network

Detailed guidance: [Task 2 — The BGPsec Lab](Task-2-bgpsec-lab.md)

Six containerized BGP routers with a complete self-signed RPKI, signing and verifying real announcements. Each step ends in a checkpoint cell (`lab.checkpoint("2.N")`) that must report all checks passed before you move on.

### Task 2.1 — The identity layer: router keys in the RPKI

Read each router's key identifier (SKI) from the key vault, then find the same SKIs in the Router Key PDUs the validator serves over RTR. Checkpoint 2.1 confirms a router key for every AS and the origin's ROA.

### Task 2.2 — Turn BGPsec on

Switch every router into BGPsec mode and confirm the real route validates on both the origin and the path axis, with every signature keyed to the SKI the RPKI publishes. Checkpoint 2.2.

### Task 2.3 — Watch the signatures accumulate

Capture BGP on each of the four inter-AS links and count the signatures in the `BGPsec_PATH` attribute on each, origin outwards. Checkpoint 2.3.

### Task 2.4 — The attack this stops

Have AS64666 announce the path forgery `64666 64602` and compare its two validation results with the real route's. Checkpoint 2.4 confirms how the forgery is rated and what policy does with it.

- [ ] **Q11** Look at both BGPsec paths. If these were normal BGP paths, which one would routers prefer?
- [ ] **Q12** Notice that the path attribute of the second path, which contains AS64666, is invalid. Use what you know about digital signatures and BGPsec to deduce why.

### Task 2.5 — The trust is revocable

Revoke AS64602's router certificate at the CA, watch what happens to the route with no router touched, then restore it. Checkpoint 2.5.

### Task 2.6 — What happens when one network has not deployed it

Switch the origin back to plain BGP while everyone else keeps BGPsec, and observe what policy does with a route that can no longer be verified. Checkpoint 2.6.

### Task 2.7 — Reflection

Answer from what you observed, citing the task step where you observed it.

- [ ] **Q13** *What a signature commits to.* In Task 2.3 the signature block grew by one per hop, and each signature covered the announcement *and the AS it was being sent to*. Why must the recipient be inside the signature? What could an AS do to defeat path validation if an AS only signed over the received hops?
- [ ] **Q14** *Two validators, two verdicts.* In Task 2.4 the same forged announcement was rated **valid** on the origin axis and **invalid** on the path axis. Is that correct? Explain where each rating comes from and what it means.
- [ ] **Q15** *Where the power went.* In Task 2.5 a route vanished from AS64604's table without any router being touched. Who, exactly, gained what power when this lab turned BGPsec on? Explain one way that power is an operational necessity and one way it is a new risk.
- [ ] **Q16** *The missing footprint.* Put Task 2.6 next to the real-world numbers (on the order of a million ROAs against a few hundred BGPsec router certificates). Using only things you observed in this exercise, give the two strongest reasons deployment looks like that. Then explain why an attacker on a partially deployed internet does not even need to forge signatures.

[README](README.md) | [Introduction](Introduction.md) | [Datasets](Datasets.md) | [Containerlab](Containerlab.md) | Tasks ⮕ | [Task 1](Task-1-concepts.md) | [Task 2](Task-2-bgpsec-lab.md) | [Notebook](nids-bgpsec.ipynb)
