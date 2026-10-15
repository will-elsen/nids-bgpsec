#!/usr/bin/env python3
"""Build the module's BGPsec lab exercise notebooks (Task 2).

    python3 containerlab/lab/tools/build_exercise.py

Writes two files from one source, at the module repo root:

    bgpsec_lab_exercise.ipynb             what students run
    bgpsec_lab_exercise_instructor.ipynb  the same, plus answers

This is the short, BGPsec-centred cut of the full curriculum notebook
(`containerlab/lab/bgpsec-lab.ipynb`, built by build_notebook.py). Where the
full lab walks the whole break-then-fix arc — hijack, ROV, forgery, BGPsec,
partial deployment — this exercise assumes the module readings covered the
attacks and goes straight at one question: how does BGPsec actually work,
on real routers, on a real wire.

Cells tagged `teacher` appear only in the instructor build.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.dirname(HERE)                      # containerlab/lab
ROOT = os.path.dirname(os.path.dirname(LAB))     # the module repo root

cells: list[tuple[str, str, bool]] = []


def md(text: str, teacher: bool = False):
    cells.append(("markdown", text.strip("\n"), teacher))


def code(text: str, teacher: bool = False):
    cells.append(("code", text.strip("\n"), teacher))


def answer(text: str):
    """A reflection answer: prompt in the student build, model answer for staff."""
    md("*Your answer:*\n\n", teacher=False)
    md("### Model answer\n\n" + text.strip("\n"), teacher=True)


# ===========================================================================
#  Front matter
# ===========================================================================

md(r"""
# Task 2 — BGPsec, on the wire

In [Understanding BGPsec](bgpsec_understanding.md) you read how
per-hop signature chains close the path-validation gap that ROV leaves open. On
the real internet, though, BGPsec's footprint is almost nothing. This exercise puts those
two facts in the same room: you
will run a small internet whose routers actually speak BGPsec, watch the
signatures accumulate hop by hop inside real BGP packets, defeat a path forgery
with them, and then see for yourself the property that explains the missing
footprint.

### What is actually running

Six BGP autonomous systems in [Containerlab](containerlab/REFERENCE.md), each
its own container, joined by dedicated point-to-point links:

```
AS64602 ──── AS64601 ──── AS64603 ──── AS64604 ──── AS64605
 origin       transit      transit      transit      observer
                                            │
                                        AS64666
                                        attacker
```

`AS64602` owns `10.64.2.0/24` and announces it; the route travels left to
right. `AS64604` is where you will do most of your watching — it peers with
the attacker, so it is the router that has to judge every claim. `AS64666`
has no special privilege of any kind: same software, its own legitimate
certificate, and nothing but the ability to send a BGP message.

Alongside the routers runs a complete, self-signed RPKI: a CA (**Krill**), a
publication point (**rsyncd**), a validator (**Routinator**), and NIST's
validation engine (**SRx-server**) that five of the routers ask for second
opinions. None of it is connected to the real RPKI — which is exactly what
makes it safe to issue, forge, and revoke things here.

Each router-to-router link is its own virtual wire. That is not cosmetic: it
is what will let you capture a single link and see precisely what one AS hands
to the next.

### If you are in a GitHub Codespace

The devcontainer has already installed containerlab and loaded the router
images, so you can run the setup cells below directly. Two things to know:

- **The first `deploy()` takes 2–3 minutes** — the RPKI plane builds a
  certificate chain from nothing.
- **If your Codespace was stopped and resumed, re-run `lab.deploy()`.** The
  virtual wires between containers do not survive a stop; `deploy()` notices
  and rebuilds everything cleanly. This is also the fix any time the lab is in
  a state you cannot explain.

Read the [Task 2 guidance page](Task-bgpsec-lab.md) if you
have not — it covers setup, timings, and what to do when something looks
stuck.
""")

# ===========================================================================
#  2.0 Setup
# ===========================================================================

md(r"""
---

## 2.0 Bring the lab up

`labkit` is the lab's driving library — every cell in this notebook goes
through it. Preflight checks this machine can host the lab and, if it cannot,
names the specific thing to fix.
""")

code(r"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path("containerlab/lab").resolve()))
import labkit as lab

lab.preflight()
""")

code(r"""
lab.deploy()
""")

md(r"""
The lab comes up with nothing validated and nothing signed — plain BGP, the
protocol running on trust. BGPsec does not replace that machinery; it rides on
the same RPKI that route origin validation (ROV) uses. So before switching it
on, give the lab
the same origin baseline the real internet has: a ROA authorising AS64602 to
originate its prefix.
""")

code(r"""
if not lab.vrp_count():
    lab.add_roa()          # 10.64.2.0/24 => AS64602, and waits for the validator

REAL = [64603, 64601, 64602]   # the legitimate path, as AS64604 sees it
lab.status()
""")

# ===========================================================================
#  2.1 The keys
# ===========================================================================

md(r"""
---

## 2.1 The identity layer: router keys in the RPKI

A ROA answers "who may originate this prefix". BGPsec needs a second kind of
statement: "this AS signs with this key". Each router in the lab holds a key
pair, and the RPKI publishes a **router certificate** binding the public key
to the AS number.

A router's key is identified by its **SKI** — Subject Key Identifier, a SHA-1
hash of the public key. It is the handle by which a signature says "here is
which key to check me with". Look at the lab's key vault:
""")

code(r"""
for asn, ski in sorted(lab.skis().items()):
    print(f"AS{asn}  SKI {ski}")
""")

md(r"""
Those are the keys as they exist on disk. Now ask the RTR feed — the same
small protocol that delivers VRPs to routers — what the *validator* is telling
routers about them:
""")

code(r"""
print(lab.rtr_dump())
""")

md(r"""
Find the `Router Key` PDUs and match one up by hand: pick an AS from the vault
listing and find its SKI in the RTR output. Same twenty bytes, arrived by a
different route — one read off disk, one delivered by the validator after
checking the certificate chain. Before this exercise is over you will see the
same value a third time, inside a packet.
""")

code(r"""
lab.check("the validator serves a router key for every AS in the lab",
          lab.router_key_count() == 6, f"{lab.router_key_count()} router keys over RTR")
lab.check("and the origin's ROA is being served alongside them",
          lab.vrp_count() == 1, f"{lab.vrp_count()} VRP(s)")
lab.checkpoint("2.1")
""")

# ===========================================================================
#  2.2 Turn it on
# ===========================================================================

md(r"""
## 2.2 Turn BGPsec on

The next cell switches every router into BGPsec mode: each one now **signs**
what it forwards and **verifies** what it receives. The switch restarts the
routing daemons, so give it a minute; the wait polls and returns as soon as
the real route is back.
""")

code(r"""
lab.set_part("c")
lab.attack("stop")                       # make sure the board is clean
lab.wait_for_best(lab.VICTIM, as_path=REAL)
""")

code(r"""
lab.show(lab.VICTIM)
""")

md(r"""
Compare this against what a plain-BGP table shows. The route has two
validation results now — **origin**, which is route origin validation (ROV)
against the ROA, and **path**, which is new. Both read `valid`.

The path result is not a lookup. To produce it, AS64604 verified a chain of
signatures: AS64602 signed the announcement to AS64601, AS64601 signed what it
received onward to AS64603, AS64603 onward to AS64604 — and every signature
checked out against a key the RPKI vouches for. Ask the router to show you the
chain it verified, and check each hop's SKI against the vault from 2.1:
""")

code(r"""
vault = lab.skis()

for asn, ski in lab.best(lab.VICTIM).segments:
    match = "matches the RPKI" if vault.get(asn) == ski else "DOES NOT MATCH"
    print(f"  AS{asn}  signed with {ski}  ({match})")
""")

md(r"""
That is the same identity seen from three directions: a key on disk, a Router
Key PDU delivered by the validator, and now a signature inside a routing
message. The agreement of the three is the entire mechanism — it is what lets
AS64604 believe a claim made by AS64602, a network it has never exchanged a
packet with.
""")

code(r"""
r = lab.best(lab.VICTIM)
lab.check("the real route validates on both axes",
          r.origin_state == "valid" and r.path_state == "valid", str(r))
lab.check("it arrived as a signed BGPsec path, not a plain one", r.signed, str(r))
lab.check("every signature is keyed to the SKI the RPKI publishes",
          all(vault.get(asn) == ski for asn, ski in r.segments) and len(r.segments) == 3,
          ", ".join(f"AS{a}" for a, _ in r.segments))
lab.checkpoint("2.2")
""")

# ===========================================================================
#  2.3 On the wire
# ===========================================================================

md(r"""
## 2.3 Watch the signatures accumulate

This is what the point-to-point topology was built for.

The next cell captures live BGP on each of the four inter-AS links in turn,
forces a re-announcement so there is something to catch, and dissects the
`BGPsec_PATH` attribute out of the packets. It takes a couple of minutes —
four captures, each with a session reset.
""")

code(r"""
growth = lab.signature_growth()

for label, hops, sigs in growth:
    print(f"{label:22} {hops} hop(s), {sigs} signature(s)")
""")

md(r"""
One signature at the origin. Two after the next AS. Three, then four. Each
network that forwards the route signs over what it received *and over the AS
it is sending to*, so the block grows by exactly one per hop and the count
always equals the length of the path.

Hold on to that detail about the recipient being inside the signature — the
first reflection question is about it, and it is the deepest fact in this
exercise.
""")

code(r"""
counts = [s for _, _, s in growth]
lab.check("the signature block grows by exactly one at each hop",
          counts == [1, 2, 3, 4], f"signatures per link, origin outwards: {counts}")
for label, hops, sigs in growth:
    lab.check(f"{label}: signatures match hop count", hops == sigs)
lab.checkpoint("2.3")
""")

# ===========================================================================
#  2.4 The attack it stops
# ===========================================================================

md(r"""
## 2.4 The attack this stops

From your Task 1 reading: the attack ROV cannot see is a **path forgery**.
AS64666 announces the victim's prefix with the path `64666 64602` — "I am
AS64666, I have a direct link to AS64602, and they told me they own this
prefix". The origin in that claim is the *real* owner, so ROV checks the
(prefix, origin) pair against the ROA and finds it authorised. On a plain-BGP
or ROV-only network, the forgery wins.

AS64666 is about to make exactly that announcement here. Note what it has: a
genuine, CA-issued router certificate of its own. It can sign. Predict, before
you run the cell, whether that helps it.
""")

code(r"""
lab.attack("forge")

# Wait for the forgery to arrive *and* be judged — a route appears in the
# table a moment before the validator has answered for it.
forged = lab.wait_for_route(lab.VICTIM, via=lab.ATTACKER_PEER, settled=True)
""")

code(r"""
lab.show(lab.VICTIM)
""")

md(r"""
Read the forged route's two validation results separately, because they
disagree, and the disagreement is the lesson.

The **origin** axis still says `valid`. The ROA authorises AS64602 to
originate this prefix; the forged path names AS64602 as origin; those agree.
ROV is fooled here exactly as it would be on the real internet — not by a bug,
but because the one claim it can test is true.

The **path** axis says `invalid`. To produce a verifiable `64666 64602`,
AS64666 needed AS64602's signature over that path — a signature naming AS64666
as the recipient. AS64602 never made one, AS64666 cannot make it without
AS64602's private key, and its own perfectly genuine key is vouched for as
AS64666, not AS64602. The chain fails at the fabricated link.
""")

code(r"""
lab.check("the forged path is rated Invalid on the path axis",
          forged.path_state == "invalid", str(forged))
lab.check("ROV is still fooled: the origin axis reads valid",
          forged.origin_state == "valid", str(forged))
lab.check("the route is dropped by policy", forged.ignored, str(forged))
lab.check("traffic follows the real, fully signed path",
          lab.best(lab.VICTIM).as_path == REAL)
lab.checkpoint("2.4")
""")

code(r"""
lab.attack("stop")
lab.wait_for_gone(lab.VICTIM, via=lab.ATTACKER_PEER)
""")

# ===========================================================================
#  2.5 Revocation
# ===========================================================================

md(r"""
## 2.5 The trust is revocable

The signatures verify because the RPKI vouches for the public keys behind
them. That vouching is a published statement, and statements can be withdrawn.

Revoke AS64602's router certificate at the CA, and watch what does **not**
happen: no router is reconfigured, no session resets, and AS64602 keeps its
private key and carries on signing exactly as before. The only thing that
changes is a certificate published by a third party.
""")

code(r"""
lab.revoke_router_key(64602)
""")

code(r"""
lab.show(lab.VICTIM)
""")

md(r"""
The route is **gone** — not de-preferred, not flagged. The only path AS64604
had now fails verification, and this configuration drops what it cannot
verify. AS64602 has not noticed: it is still announcing, still signing, still
sending the same bytes down the same wire. Everything that changed happened at
a certificate authority and travelled to the routers as data.

Worth sitting with: the power to remove a live route from the internet now
rests with whoever operates the CA, not with the networks carrying the route.
Whether that is an operational capability or a new single point of failure
depends entirely on who holds the key — remember this when you answer
reflection question 3.

Put it back before moving on:
""")

code(r"""
after = lab.routes(lab.VICTIM)
lab.check("no path to the prefix verifies any more",
          not any(r.path_state == "valid" for r in after),
          "; ".join(str(r) for r in after) or "no path to the prefix at all")

lab.restore_router_key(64602)
lab.wait_for_best(lab.VICTIM, as_path=REAL)
lab.checkpoint("2.5")
""")

# ===========================================================================
#  2.6 The chain needs every link
# ===========================================================================

md(r"""
## 2.6 What happens when one network has not deployed it

Everything so far assumed all five networks on the path speak BGPsec. On the real
internet that assumption fails badly: the global RPKI holds a few
hundred router certificates, against millions of routes.

So run the honest version. The next cell switches the lab into **partial
deployment**: the origin, AS64602, goes back to plain BGP — no keys, no
signatures — while everyone else keeps BGPsec on. And because dropping every
unverifiable route would now mean disconnecting from the unsigned majority,
the routers' policy weakens from *drop* to *de-prefer*.
""")

code(r"""
lab.set_part("d")
lab.attack("stop")
lab.wait_for_best(lab.VICTIM, as_path=REAL)
""")

code(r"""
lab.show(lab.VICTIM)
lab.show(lab.OBSERVER)
""")

md(r"""
The route still arrives — a network that has not deployed BGPsec is not cut
off. But look at what became of the guarantee. The origin never signed, so the
chain was never started, and no downstream router can verify anything: path
`invalid` at AS64604, and at the far end AS64605 can still prove *who owns the
prefix* — ROV works regardless — but nothing at all about the path.

Four networks paid the full cost of deployment here. Because one did not, all
four got nothing for it.
""")

code(r"""
r = lab.best(lab.VICTIM)
lab.check("the route still arrives — a non-BGPsec network is not cut off",
          r.as_path == REAL, str(r))
lab.check("but the path can no longer be verified",
          r.path_state == "invalid", str(r))
lab.check("and it is de-preferred rather than dropped",
          r.best and r.localpref <= r.localpref_base, str(r))
obs = lab.best(lab.OBSERVER)
lab.check("at the far end: origin provable, path not signed at all",
          obs.origin_state == "valid" and not obs.signed, str(obs))
lab.checkpoint("2.6")
""")

# ===========================================================================
#  Reflection
# ===========================================================================

md(r"""
---

## Reflection questions

Answer from what you observed, citing the section where you observed it.

### Question 1 — what a signature commits to

In 2.3 the signature block grew by one per hop, and each signature covered
the announcement *and the AS it was being sent to*. Why must the recipient be
inside the signature? Describe concretely what an AS that legitimately
receives a signed route could do if signatures named only their senders.
""")

answer(r"""
Without the recipient, a signature is a transferable object: it says only
"AS X forwarded this route", to no one in particular. Any AS legitimately
holding a signed announcement could then replay the block to a network it was
never sent to — presenting cryptographic proof of a path it is not actually
on, or re-announcing a route into a part of the internet where that path is a
lie, with every signature still verifying.

Signing *toward* a named recipient makes each signature valid for exactly one
link. Replayed anywhere else, it is a signature over the wrong recipient AS
and verification fails. That is what turns the chain from a collection of
endorsements — which could be recombined into a path nobody ever announced —
into a proof that *this specific route travelled this specific sequence of
links*.

The full-credit observation: this is also the fact with the price tag. Because
a signature names its recipient, it cannot be computed once and reused; a
route announced to fifty peers needs fifty distinct signatures. The security
property and the deployment cost are the same design decision.
""")

md(r"""
### Question 2 — two validators, two verdicts

In 2.4 the same forged announcement was rated **valid** on the origin axis
and **invalid** on the path axis, and both verdicts were *correct*. State
precisely what claim each validator tested. What does this pair of verdicts
tell you about what a ROA can and cannot say?
""")

answer(r"""
Origin validation tested: *does some ROA authorise the AS at the end of this
path — AS64602 — to originate 10.64.2.0/24?* Answer: yes. That claim is true;
the ROA exists and says exactly that. ROV validates a (prefix, origin) pair
and is blind to every other element of the path by construction.

Path validation tested a different claim: *did each AS named in this path
actually receive this announcement and forward it to the next one — can every
hop be verified against a signature made with a key the RPKI binds to that
AS?* Answer: no. The 64602→64666 hop has no valid signature, because the
adjacency was invented.

The lesson about ROAs: a ROA is a statement about origination only. It cannot
speak about paths because the prefix holder cannot know, at signing time, what
paths will exist, and has no authority over other networks anyway. The forgery
is engineered to make its one checkable claim true and put the lie somewhere
origin validation cannot look. It takes a second, different kind of statement
— a router certificate plus per-hop signatures — to make the path itself
checkable.
""")

md(r"""
### Question 3 — where the power went

In 2.5 a route vanished from AS64604's table without any router being
touched. Who, exactly, gained what power when this lab turned BGPsec on? Name
one way that power is an operational necessity and one way it is a new risk —
and one thing about how this lab's RPKI is built that made exercising it so
clean.
""")

answer(r"""
The CA operator — whoever can publish and revoke certificates under the trust
anchor — gained the ability to make any signed route stop verifying,
everywhere, without cooperation from any network on the path. Routers act on
that decision automatically, as data delivered through the validator.

As necessity: revocation is the only remedy that works at routing speed when a
router's private key is compromised. An attacker holding a stolen key can sign
valid-looking paths; no per-router reconfiguration across the internet could
plausibly respond, but one published revocation reaches every validator within
minutes. A defence built on certificates without workable revocation would be
strictly weaker.

As risk: the same lever removes *legitimate* routes. A CA compromise, a legal
order against the CA's jurisdiction, or plain operational error at the CA now
propagates to the data plane of networks that never agreed to anything except
"validate signatures". Networks running strict drop policy — like this lab in
2.5 — turn a certificate mistake into an outage.

What made it clean here: the lab runs a single, self-signed RPKI — one CA, one
trust anchor, that the lab itself controls. The real RPKI distributes this
power across five RIR trust anchors and delegated CAs, which softens the
single point of failure but does not eliminate the structure: someone other
than the route's operators can always, by design, withdraw the vouching.
""")

md(r"""
### Question 4 — the missing footprint

Put 2.6 next to the real-world numbers (on the order of a million ROAs against
a few hundred BGPsec router certificates). Using only things you observed in
this exercise, give the two strongest reasons deployment looks like that.
Then explain why an attacker on a partially deployed internet does not even
need to forge signatures.
""")

answer(r"""
**Reason one — the first mover gets nothing (2.6).** BGPsec's guarantee is a
chain, and value appears only when every AS on a path has deployed. In 2.6
four of five networks paid the full cost — keys, certificates, signing and
verifying on every update — and received zero security benefit because the
fifth did not. A ROA, by contrast, delivers benefit to its publisher
immediately and unilaterally: everyone doing ROV starts protecting your prefix
the day you publish. One technology has a bootstrapping problem; the other is
the reason the global RPKI holds a million of them.

**Reason two — the cost is per-neighbour and unavoidable (2.3 / Q1).** Each
signature commits to its recipient, so signatures cannot be computed once and
shared. A real router announcing a full table to many peers must produce a
distinct signature per route per peer and verify chains on everything it
receives — sustained public-key cryptography in the most performance-sensitive
part of a network, on hardware with decade-long replacement cycles.

**Why no forgery is needed.** 2.6 showed the necessary policy concession: on
a partially deployed internet, unverifiable routes must be accepted (merely
de-preferred), or you disconnect from the unsigned majority. So an attacker
simply announces a *plain BGP* route — no signatures at all. It cannot be
verified, but it cannot be rejected either. Partial BGPsec therefore degrades
from a guarantee into a preference for signed paths, and a preference is a
much weaker thing than the protocol's design promises. The defence only
becomes a defence once nearly everyone runs it — which is precisely the
deployment the economics prevent.
""")

# ===========================================================================
#  Wrap up
# ===========================================================================

md(r"""
---

## Finishing up

Reset puts the lab back to its starting state; destroy tears the containers
down entirely. In a Codespace, stopping the machine achieves the same thing —
just remember that resuming means `lab.deploy()` again.
""")

code(r"""
lab.reset()
# lab.destroy()
""")

md(r"""
### If you want the whole story

This exercise dropped you into a working defence. The full lab notebook —
[`containerlab/lab/bgpsec-lab.ipynb`](containerlab/lab/bgpsec-lab.ipynb) —
runs the arc this module's readings describe, in the order the real internet
lived it: hijack a prefix on unprotected BGP, deploy RPKI and watch it stop
the hijack, defeat your own defence with the forgery from 2.4, and only then
deploy BGPsec. Every section of this exercise appears there with more room
around it. The lab is already deployed; the notebook starts with the same
`deploy()` and is safe to run from the top.
""")

md(r"""
---

## Instructor notes

**Running time.** 45–60 minutes. The slow cells are `deploy()` (2–3 minutes),
`signature_growth()` (~2 minutes, four captures with session resets), and the
two `set_part()` switches (45–70 seconds each; the waits poll, so a cell that
seems to hang is usually converging).

**Codespaces.** The devcontainer loads images and installs Python deps in
postCreate. The one recurring support case is a resumed Codespace: containers
restart without their virtual wires, everything shows Up, nothing errors, and
no routes move. The fix is always `lab.deploy()` again. Students who read the
front matter know this; students who did not will file it as "the lab is
broken".

**Where students get stuck.**

1. *Re-running an observation cell before convergence.* `lab.show()` is a
   snapshot; the `wait_for_*` helpers poll. Re-running is safe and idempotent.
2. *2.4 run twice without `attack("stop")`.* The stop cell after the checks
   exists so 2.5 starts clean; if a student reruns the forgery out of order,
   `lab.attack("stop")` then re-running the section recovers.
3. *Sessions Established but no routes anywhere.* Stale validation-engine
   client table; `lab.set_part("c")` (or the current part) restarts it in the
   right order. Rare since set_part restarts srx_server first.

**Grading.** Q1 is the hardest and the most important; it is reasonable for
students to need the recipient-signing answer given to them, and the useful
check is whether they can then explain what breaks without it. Q2 separates
students who followed the mechanism from those who pattern-matched "validation
failed". Q4 should cite 2.6 and the real-world counts, not opinion; the plain-BGP
downgrade attack is the discriminator between a complete answer and a good
one.

**The moment that matters** is the pair of verdicts in 2.4. If a student is
skimming, slow them down there and have them predict both axes before running
the cell.
""", teacher=True)


# ===========================================================================
#  Emit
# ===========================================================================

def build(path: str, include_teacher: bool):
    nb = {
        "cells": [
            {
                "cell_type": kind,
                "metadata": {},
                "source": text.splitlines(keepends=True),
                **({"outputs": [], "execution_count": None} if kind == "code" else {}),
            }
            for kind, text, teacher in cells
            if include_teacher or not teacher
        ],
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python", "version": "3"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(nb, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    kinds = [c["cell_type"] for c in nb["cells"]]
    print(f"{os.path.basename(path)}: {len(kinds)} cells "
          f"({kinds.count('markdown')} markdown, {kinds.count('code')} code)")


if __name__ == "__main__":
    build(os.path.join(ROOT, "bgpsec_lab_exercise.ipynb"), include_teacher=False)
    build(os.path.join(ROOT, "bgpsec_lab_exercise_instructor.ipynb"), include_teacher=True)
