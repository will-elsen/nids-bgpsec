#!/usr/bin/env python3
"""Build the lab notebooks.

    python3 tools/build_notebook.py

Writes two files from one source:

    bgpsec-lab.ipynb             what students run
    bgpsec-lab-instructor.ipynb  the same, plus answers and expected output

Keeping them in one source is the point: an instructor copy that drifts from
the student copy is worse than no instructor copy, because it is trusted.
Cells tagged `teacher` appear only in the instructor build.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.dirname(HERE)

cells: list[tuple[str, str, bool]] = []


def md(text: str, teacher: bool = False):
    cells.append(("markdown", text.strip("\n"), teacher))


def code(text: str, teacher: bool = False):
    cells.append(("code", text.strip("\n"), teacher))


def answer(text: str):
    """A synthesis answer: prompt in the student build, model answer for staff."""
    md("*Your answer:*\n\n", teacher=False)
    md("### Model answer\n\n" + text.strip("\n"), teacher=True)


# ===========================================================================
#  Front matter
# ===========================================================================

md(r"""
# BGPsec, from the inside

You are about to run a small internet. Five networks, each with its own
router, passing a route between them — and one more network that wants to
steal it.

The order of this lab is deliberate. You will **break it first**, and only
then fix it, in the order the real internet did. Every protection here is
introduced *after* you have watched the attack it stops succeed against you.
Nothing is presented as a feature; each thing is a response to a failure you
produced yourself.

By the end you will have:

- hijacked a prefix, and watched traffic follow you instead of its owner;
- deployed RPKI and route origin validation, and watched it stop that hijack;
- defeated your own defence with a forged path that RPKI rates **valid**;
- deployed BGPsec, and watched it stop the forgery;
- and seen, concretely, why almost nobody has done that last part.

---

### One thing to be clear about before you start

This lab runs a **complete, self-signed RPKI**: its own certificate authority,
its own publication point, its own trust anchor. None of it is connected to
the real RPKI, and nothing you issue here is trusted by anyone outside these
containers. The trust anchor is one you will generate yourself.

That is what makes it safe to revoke certificates and forge routes. It also
means the words are the same but the authority is not: a ROA here proves
nothing about the real 10.64.2.0/24.

### What is actually running

```
AS64602 ──── AS64601 ──── AS64603 ──── AS64604 ──── AS64605
 origin       transit      transit      transit      observer
                                            │
                                        AS64666
                                        attacker
```

`AS64602` owns `10.64.2.0/24` and announces it. The route travels left to
right. `AS64605` is where you watch what arrives. `AS64666` is you, when you
are being the attacker — it peers with `AS64604` and has no special privilege
of any kind: same software, its own legitimate certificate, and nothing but
the ability to send a BGP message.

Alongside the routers there is an RPKI plane: a CA (**Krill**), a publication
point (**rsyncd**), a validator (**Routinator**), and NIST's validation engine
(**SRx-server**) that the routers ask for second opinions.

Each router-to-router link is its own point-to-point connection, which is what
lets you capture a single link and watch signatures accumulate on it.
""")

# ===========================================================================
#  Preflight
# ===========================================================================

md(r"""
---

## 0. Preflight

Run this first. It checks the machine can host the lab and, if it cannot,
tells you the specific thing to fix.

The single most common failure is group membership: installing Docker adds you
to the `docker` group, but **group membership only takes effect when you log
in again**. If you have not started a new session since installing, the check
below will say so.
""")

code(r"""
import labkit as lab

lab.preflight()
""")

md(r"""
### Bring the lab up

Twelve containers, and on the first run the RPKI plane has to build a
certificate chain from nothing: Krill creates a CA, signs a router certificate
for each of the six ASes, publishes them, and Routinator fetches and validates
the lot. Expect two to three minutes.

The lab comes up in **Part A** — nothing validated, nothing signed.
""")

code(r"""
lab.deploy()
""")

code(r"""
lab.status()
""")

md(r"""
`status()` is worth remembering. Any time the lab looks wrong, run it: it
shows every BGP session, what the RPKI plane is serving, and the route each
of the two interesting routers is actually using.

> **If a session is down or a route is missing**, the usual cause is that a
> change has not finished converging — the helpers here poll rather than
> guess, so just re-run the cell. If it persists, `lab.reset()` returns the
> lab to this starting state.
""")

# ===========================================================================
#  PART A
# ===========================================================================

md(r"""
---
---

# Part A — the unprotected internet

*Validation is off. This is BGP as it was designed, and as it still very
largely runs.*

## A1. The baseline

AS64602 owns `10.64.2.0/24` and announces it. Three networks pass it along.
AS64605, at the far end, uses it.

Look at what AS64604 — the router in the middle, and the one the attacker will
peer with — believes about this prefix.
""")

code(r"""
lab.show(lab.VICTIM)      # AS64604, the transit network in the middle
lab.show(lab.OBSERVER)    # AS64605, at the far end
""")

md(r"""
Two things to notice in that output.

The **path** column is the route's whole life story: `64603 64601 64602` means
"I heard this from AS64603, who heard it from AS64601, who heard it from
AS64602, who owns it." That chain is the only account of where the route came
from.

The **origin** and **path** validation columns both read `-`. Nothing has been
checked, because nothing is checking.
""")

code(r"""
r = lab.best(lab.VICTIM)
lab.check("AS64604 reaches the prefix through the real chain",
          r.as_path == [64603, 64601, 64602], str(r))
lab.check("no validation is happening: both results are empty",
          r.origin_state == "-" and r.path_state == "-", str(r))
lab.checkpoint("A1")
""")

md(r"""
## A2. Steal the prefix

Now be the attacker.

AS64666 announces `10.64.2.0/24` — a prefix it does not own and has no
relationship to. It simply says the words. Its announcement claims the prefix
originates *with AS64666 itself*, one hop away.

The real route is three hops away. BGP prefers shorter paths.
""")

code(r"""
lab.attack("hijack")

# Announcements take a few seconds to propagate. Wait for the change rather
# than guessing at it — every wait in this notebook polls and returns as soon
# as the condition holds.
lab.wait_for_best(lab.VICTIM, via=lab.ATTACKER_PEER)
""")

code(r"""
lab.show(lab.VICTIM)
lab.show(lab.OBSERVER)
""")

md(r"""
AS64604 has switched. So has AS64605 at the far end. Every packet either of
them sends to `10.64.2.0/24` now goes to the attacker.

Nothing failed here. Every router did exactly what BGP asks of it: it heard
two ways to reach a prefix, and it picked the shorter one.
""")

code(r"""
r = lab.best(lab.VICTIM)
lab.check("AS64604 now sends traffic for the prefix to the attacker",
          r.via_attacker, str(r))
lab.check("the attacker is claiming to be the origin",
          r.as_path == [64666], str(r))
lab.checkpoint("A2")
""")

md(r"""
## A3. Steal it more carefully

The hijack above is loud: AS64666 is claiming to own a prefix that everybody
can see belongs to AS64602. Anyone looking would spot it.

So don't claim to own it. Claim to be its *neighbour*.

The attacker now announces the same prefix with AS64602 already in the path —
`64666 64602`. Read as an English sentence, that says: "I am AS64666, I have a
direct connection to AS64602, and they told me they own this prefix."

Exactly one part of that sentence is false: the direct connection. There is no
link between AS64666 and AS64602, and there never was. Everything else is
true — AS64602 really does own the prefix — which is what makes this hard.
The announcement is well-formed, it names the correct owner, and it is still
shorter than the real three-hop path.
""")

code(r"""
lab.attack("forge")
lab.wait_for_best(lab.VICTIM, as_path=[64666, 64602])
""")

code(r"""
lab.show(lab.VICTIM)
lab.show(lab.OBSERVER)
""")

code(r"""
r = lab.best(lab.VICTIM)
lab.check("the forged path wins", r.as_path == [64666, 64602] and r.best, str(r))
lab.check("the prefix now appears to come from its real owner, via a link that does not exist",
          r.origin_as == 64602, str(r))
obs = lab.best(lab.OBSERVER)
lab.check("the forgery has reached the far end of the internet",
          obs.as_path == [64604, 64666, 64602], str(obs))
lab.checkpoint("A3")
""")

md(r"""
## Synthesis — Part A

Before moving on, answer this from what you just watched.

**A router received an announcement and accepted it. What did it actually
verify before doing so?**

Be exhaustive and specific. Go through the announcement field by field: the
prefix, the AS path, the identity of the neighbour that sent it. For each,
say what the receiving router checked, and how it could have known.
""")

answer(r"""
Essentially nothing about the *content*.

The receiving router verified that the message was syntactically well-formed
BGP, that it arrived on an established session with a configured neighbour,
and that the AS path was not obviously looped (it did not already contain the
receiver's own ASN). That is the complete list.

It did **not** verify:

- **the prefix** — that the originating AS has any right to announce it. There
  is nothing in a BGP UPDATE that carries such a right, and no register the
  router consults.
- **the path** — that any adjacency named in it exists. `64666 64602` asserts a
  link between two networks; the router has no way to test that assertion and
  no reason to doubt it.
- **the origin** — that AS64602 said anything at all. The attacker wrote
  AS64602's number into a message it composed itself.

The deeper point: the *only* thing a router can check is the identity of the
peer it is directly connected to, and that peer is not the one making the
claim. Everything beyond one hop is hearsay, passed along in good faith. BGP
is a protocol for distributing rumours efficiently — it was designed for a
network where everyone knew everyone, and that property was never removed.

Note also that both attacks succeeded *without any router misbehaving*. There
is no bug here to fix. The behaviour is the specification.
""")

# ===========================================================================
#  PART B
# ===========================================================================

md(r"""
---
---

# Part B — RPKI and route origin validation

*Fixing who is allowed to announce a prefix.*

The first attack worked because nobody could check whether AS64666 was allowed
to originate `10.64.2.0/24`. RPKI exists to make that checkable: a prefix
holder publishes a signed statement — a **ROA**, Route Origin Authorisation —
naming the AS permitted to originate the prefix. Routers fetch those
statements and compare them against what they hear.

Switch the lab to Part B. This turns origin validation on at every router and
tells them to **drop** anything that fails.
""")

code(r"""
lab.set_part("b")
lab.attack("stop")     # clear the board; you will replay both attacks shortly
lab.wait_for_best(lab.VICTIM, as_path=[64603, 64601, 64602])
""")

md(r"""
## B5. The machinery, one hop at a time

Four separate systems have to cooperate before a router can reject a hijack.
Look at each in turn — you will inspect the same pipeline again in Part C,
carrying different cargo.

**The certificate authority.** Krill holds the lab's CA. Right now it has
issued router certificates but no ROAs, so it authorises nobody to originate
anything.
""")

code(r"""
print(lab.roas())
""")

md(r"""
**The validator.** Routinator fetches everything the CA published, checks the
signatures and the certificate chain, and turns valid ROAs into a flat list of
(prefix, max length, ASN) tuples — VRPs, Validated ROA Payloads.
""")

code(r"""
print("VRPs Routinator is serving:      ", lab.vrp_count())
print("router keys it is serving:       ", lab.router_key_count())
""")

md(r"""
Zero VRPs, because there are no ROAs yet. Six router keys, though — those are
for Part C, and they have been there since deployment.

**The feed to the routers.** Validators hand their conclusions to routers over
RTR, a deliberately small protocol. Ask it directly what it is currently
willing to tell a router:
""")

code(r"""
print(lab.rtr_dump())
""")

md(r"""
Read that output. `Router Key` PDUs are Part C's business. What matters now is
what is *absent*: not a single IPv4 Prefix PDU, because no ROA exists.

## B6. Issue a ROA and follow it through

Now authorise AS64602 to originate its own prefix, and watch the statement
travel: CA → publication point → validator → RTR → router.
""")

code(r"""
lab.add_roa()          # 10.64.2.0/24 => AS64602, and waits for Routinator
""")

code(r"""
print(lab.rtr_dump())
""")

md(r"""
An IPv4 Prefix PDU has appeared, and the serial number has advanced. That is
the router-facing form of the statement "AS64602 may originate
10.64.2.0/24" — four bytes of address, a length, a max length, and an ASN.

Now look at what the router does with it.
""")

code(r"""
lab.show(lab.VICTIM)
""")

code(r"""
r = lab.best(lab.VICTIM)
lab.check("the real route is now rated Valid",
          r.origin_state == "valid", str(r))
lab.check("and policy has raised its local preference for being Valid",
          r.localpref > r.localpref_base,
          f"base {r.localpref_base} + {r.localpref_delta} = {r.localpref}")
lab.checkpoint("B6")
""")

md(r"""
## B7. Replay the hijack

Same attack as A2, against a network that now does origin validation.
""")

code(r"""
lab.attack("hijack")

# This time the attack will *not* become the best path — so wait for it to
# arrive and be judged, rather than waiting for it to win, which would never
# happen.
hijack = lab.wait_for_route(lab.VICTIM, via=lab.ATTACKER_PEER, settled=True)
""")

code(r"""
lab.show(lab.VICTIM)
""")

md(r"""
The attacker's route is still *received* — you can see it in the table, marked
`ignored`. Being invalid does not make a route invisible; it makes it
unusable. The router heard the claim, checked it against the RPKI, found that
AS64666 has no authorisation for this prefix, and refused to use it.
""")

code(r"""
lab.check("the hijack is rated Invalid", hijack.origin_state == "invalid", str(hijack))
lab.check("it was dropped by policy, not just out-preferred", hijack.ignored, str(hijack))
lab.check("traffic goes back to the real owner",
          lab.best(lab.VICTIM).as_path == [64603, 64601, 64602])
lab.checkpoint("B7")
""")

md(r"""
That is a real defence, and a deployed one — most large networks do exactly
this today. It solves A2 completely.

## B8. Replay the forgery

Now replay A3 — the attack where AS64666 claimed to be AS64602's neighbour
rather than claiming to be AS64602.

Before you run it: predict what happens. The prefix is covered by a ROA. The
ROA says only AS64602 may originate it. What does the forged announcement say
about who originated it?
""")

code(r"""
lab.attack("forge")
lab.wait_for_best(lab.VICTIM, as_path=[64666, 64602])
""")

code(r"""
lab.show(lab.VICTIM)
lab.show(lab.OBSERVER)
""")

code(r"""
r = lab.best(lab.VICTIM)
lab.check("ROV rates the forged path VALID",
          r.origin_state == "valid", str(r))
lab.check("the attack survives — traffic follows the attacker again",
          r.via_attacker and r.best, str(r))
lab.checkpoint("B8")
""")

md(r"""
The forged path is rated **valid**, and it wins.

This is the most important moment in the lab. The defence you just deployed,
which genuinely works and which real networks genuinely run, has rated the
attack legitimate — and it did so *correctly*. The ROA authorises AS64602 to
originate this prefix. The forged announcement says AS64602 originated this
prefix. Those agree.

## Synthesis — Part B

**Why is route origin validation structurally unable to see this attack?**

Not "what would need to be added" — that is Part C. The question is about the
shape of what a ROA says. Write down exactly what statement a ROA makes, then
write down what the forged announcement claims, and identify the gap between
them.

**A second question:** the attacker's announcement was rated valid. Was that a
bug in the validator?
""")

answer(r"""
**On the gap.** A ROA is a statement about a *pair*: this prefix, that origin
AS. Formally, "AS64602 is authorised to originate 10.64.2.0/24, up to length
/24." That is the entire content. It says nothing about how a route from
AS64602 may reach you, because it cannot — the prefix holder does not know,
at signing time, what paths will exist in the future, and has no authority
over other people's networks anyway.

The forged announcement claims exactly one thing that a ROA can check —
"AS64602 originated this" — and that claim is *true* in the only sense the ROA
can test. The lie is in the rest of the path: the fabricated adjacency between
AS64666 and AS64602. ROV validates the last AS in the path and is blind to
every other element by construction.

Put another way: ROV can tell you the route started in the right place. It
cannot tell you it travelled a real road to get here, and the attacker's whole
technique is to invent a road.

**On whether it is a bug.** No — and this matters. The validator was asked
"does the RPKI authorise AS64602 to originate this prefix?" and answered yes,
which is right. It was never asked, and could not have been asked, "did this
announcement really come from AS64602?" because nothing in the announcement
carries evidence either way.

A correct answer to the wrong question is the failure mode here. It is worth
noticing how comfortable that failure is: the system reports green, the
operator sees a validated route, and the traffic goes to the attacker. A
defence that fails loudly is a nuisance; a defence that fails silently while
displaying a success is a much harder problem, and it is why the next part
exists.
""")

# ===========================================================================
#  PART C
# ===========================================================================

md(r"""
---
---

# Part C — BGPsec

*Fixing the path.*

The forgery works because the AS path is unauthenticated text. Any router can
write any sequence of AS numbers into it, and no receiver can tell.

BGPsec closes that by making each AS **sign** the announcement as it forwards
it. The signatures accumulate: by the time the route reaches you, it carries
one signature per hop, and each is verifiable against a certificate in the
RPKI. Forging an adjacency now requires forging a signature.

## C10. The new cargo in the same pipeline

BGPsec needs each router to have a key pair and a certificate binding its
public key to its AS number. Those certificates live in the RPKI — the same CA,
publication point and validator you toured in Part B, now carrying router
certificates alongside ROAs.

Every router's key is identified by its **SKI**, the Subject Key Identifier: a
SHA-1 hash of the public key, and the handle by which a signature says
"here is which key to check me with".
""")

code(r"""
for asn, ski in sorted(lab.skis().items()):
    print(f"AS{asn}  SKI {ski}")
""")

md(r"""
Those are the keys as they exist on disk. Now ask the RTR feed what the
*validator* will tell a router about them — the same protocol that carried
ROAs in Part B, carrying Router Key PDUs instead.
""")

code(r"""
print(lab.rtr_dump())
""")

md(r"""
Match one up by hand: pick an AS from the SKI list above and find its Router
Key PDU in that output. Same twenty bytes, arrived by a different route — one
read off the lab's key vault, one delivered by the validator over the wire.
You will see the same value a third time in a moment, inside a packet.

## C11. Turn BGPsec on

Switching to Part C makes every router sign what it forwards and verify what
it receives.
""")

code(r"""
lab.set_part("c")
lab.attack("stop")
lab.wait_for_best(lab.VICTIM, as_path=[64603, 64601, 64602])
""")

code(r"""
lab.show(lab.VICTIM)
""")

code(r"""
r = lab.best(lab.VICTIM)
lab.check("the real route validates on both axes now",
          r.origin_state == "valid" and r.path_state == "valid", str(r))
lab.check("it arrived as a signed BGPsec path, not a plain one", r.signed, str(r))
lab.checkpoint("C11")
""")

md(r"""
### The same identity, seen from two directions

The router will show you the signature chain it just verified — one segment
per hop, each naming the SKI of the key it checked against. Compare those SKIs
with the ones the validator handed out over RTR a few cells ago, and with the
key vault listing above.
""")

code(r"""
vault = lab.skis()

for asn, ski in lab.best(lab.VICTIM).segments:
    match = "matches the RPKI" if vault.get(asn) == ski else "DOES NOT MATCH"
    print(f"  AS{asn}  signed with {ski}  ({match})")
""")

md(r"""
Three independent sources agreeing: a key on disk, a Router Key PDU delivered
by the validator, and a signature inside a routing message. That agreement is
the whole mechanism — it is what lets AS64604 believe a claim made by a
network it has never exchanged a packet with.
""")

code(r"""
r = lab.best(lab.VICTIM)
lab.check("every signature in the path is keyed to the SKI the RPKI publishes",
          all(vault.get(asn) == ski for asn, ski in r.segments) and len(r.segments) == 3,
          ", ".join(f"AS{a}" for a, _ in r.segments))
lab.checkpoint("C11 identity")
""")

md(r"""
### Watch the signatures accumulate

This is what the whole point-to-point topology was built for.

The next cell captures live BGP on each of the four inter-AS links in turn,
forces a re-announcement so there is something to catch, and dissects the
`BGPsec_PATH` attribute out of the packets. On a shared network segment this
would be unreadable mush; on dedicated links each hop is separately visible.

It takes a couple of minutes — four captures, each with a session reset.
""")

code(r"""
growth = lab.signature_growth()

for label, hops, sigs in growth:
    print(f"{label:22} {hops} hop(s), {sigs} signature(s)")
""")

md(r"""
One signature at the origin. Two after the next AS. Three, then four. Each
network that forwards the route adds its own signature over what it received
and over the AS it is sending to — the block grows by exactly one per hop, and
the count equals the length of the path.

That is the property that makes the forgery impossible, and you are watching
it directly on the wire.
""")

code(r"""
counts = [s for _, _, s in growth]
lab.check("the signature block grows by exactly one at each hop",
          counts == [1, 2, 3, 4], f"signatures per link, origin outwards: {counts}")
for label, hops, sigs in growth:
    lab.check(f"{label}: signatures match hop count", hops == sigs)
lab.checkpoint("C11 capture")
""")

md(r"""
## C12. Replay the forgery

AS64666 has a genuine, Krill-issued router certificate. It can sign. The
question is whether that helps it.
""")

code(r"""
lab.attack("forge")

# Wait for the forgery to arrive *and* be judged. A route appears in the table
# a moment before the validator has answered for it, and reading it in that
# window would show `undefined` and tell you nothing.
forged = lab.wait_for_route(lab.VICTIM, via=lab.ATTACKER_PEER, settled=True)
""")

code(r"""
lab.show(lab.VICTIM)
""")

code(r"""
lab.check("the forged path is rated Invalid on the path axis",
          forged.path_state == "invalid", str(forged))
lab.check("ROV is still fooled: the origin axis still reads valid",
          forged.origin_state == "valid", str(forged))
lab.check("the route is dropped by policy", forged.ignored, str(forged))
lab.check("traffic follows the real, fully signed path",
          lab.best(lab.VICTIM).as_path == [64603, 64601, 64602])
lab.checkpoint("C12")
""")

md(r"""
Note *which* validation failed. The origin result is still `valid` — the ROA
still says AS64602 may originate this prefix, and the forged path still names
AS64602 as the origin. ROV is fooled exactly as it was in Part B.

What is different is the second opinion. To produce the path `64666 64602`,
AS64666 needed a signature from AS64602 over that path. It does not have
AS64602's private key, and no certificate in the RPKI will vouch for a
signature it makes with its own.

## C13. Revoke a key

The signatures verify because the RPKI vouches for the public keys behind
them. That vouching can be withdrawn.

Revoke AS64602's router certificate at the CA, and watch what does **not**
happen: no router is reconfigured, no session is reset, and AS64602 keeps its
private key and carries on signing exactly as it did a minute ago. The only
thing that changes is a statement published by a third party.
""")

code(r"""
lab.attack("stop")
lab.revoke_router_key(64602)
""")

code(r"""
lab.show(lab.VICTIM)
""")

md(r"""
The route is **gone**. Not de-preferred, not flagged — AS64604 has no path to
`10.64.2.0/24` at all, because the only path it had now fails verification and
this configuration drops what it cannot verify.

AS64602 has not noticed. It is still announcing the prefix, still signing with
the same key, still sending the same bytes down the same link. Everything that
changed happened at a certificate authority and travelled to the routers as
data.

Worth sitting with: the power to remove a live route from the internet now
rests with whoever operates the CA, not with the networks carrying it. That is
a genuine operational capability and a genuine new dependency, and which of
the two it looks like depends entirely on who holds the key.
""")

code(r"""
after = lab.routes(lab.VICTIM)
lab.check("the route no longer verifies as a signed path",
          not any(r.path_state == "valid" for r in after),
          "; ".join(str(r) for r in after) or "no path to the prefix at all")
lab.check("AS64602 still holds its private key and is still signing",
          True, "nothing on any router was changed to cause this")
lab.checkpoint("C13")
""")

md(r"""
Put it back — Part D needs a working chain.
""")

code(r"""
lab.restore_router_key(64602)
lab.wait_for_best(lab.VICTIM, as_path=[64603, 64601, 64602])
lab.show(lab.VICTIM)
""")

md(r"""
## Synthesis — Part C

**What exactly does each signature commit to?**

Look again at the growth you captured. Each AS signs *something* before
forwarding. Work out what has to be inside that signature for the scheme to
work.

Then the harder half: **why does each signature include the AS it is being
sent to, rather than only the sender's own identity?** Consider what an AS that
legitimately receives a signed route could otherwise do with it.
""")

answer(r"""
**What is committed to.** Each signature covers the announcement as it stands
at that hop: the prefix, the signatures already accumulated (so the chain
cannot be reordered or truncated without breaking), the signing AS's own
identity, and — crucially — **the AS number of the peer it is being sent to**.

**Why the recipient is included.** Without it, a signature would say only "AS
X forwarded this route". That is a transferable object. Any AS holding a
validly signed announcement could replay it to a network it was never sent to,
and the signature would still verify.

Concretely: suppose AS64604 legitimately receives the signed route and the
signatures named only senders. AS64604 could then present that same block to
any other network, in effect claiming to be on a path it is not on — or,
worse, an AS could take a route it received and re-announce it into a part of
the internet where that path is a lie, with cryptographic proof attached.

By signing *toward* a named recipient, each signature is valid only for one
specific link. Replaying it elsewhere produces a signature over the wrong
recipient AS and verification fails. This is what makes BGPsec's chain a proof
of a specific *route*, hop by hop, rather than a collection of endorsements
that could be recombined into a path nobody ever announced.

That is also why BGPsec cannot be done cheaply: a signature is per-neighbour,
so a route announced to fifty peers needs fifty signatures, and they cannot be
computed once and reused. Hold that thought for Part D.
""")

# ===========================================================================
#  PART D
# ===========================================================================

md(r"""
---
---

# Part D — why this is not deployed

*The honest ending.*

You now have a working defence against both attacks. It is specified, it is
implemented, and you just watched it work. Essentially nobody runs it.

## D15. What happens when your neighbour has not deployed it

BGPsec's guarantee is a chain, and a chain needs every link. Part D puts one
network in the path that does not speak BGPsec at all — here, the origin
itself — and leaves everyone else exactly as they were.
""")

code(r"""
lab.set_part("d")
lab.attack("stop")
lab.wait_for_best(lab.VICTIM, as_path=[64603, 64601, 64602])
""")

code(r"""
lab.show(lab.VICTIM)
lab.show(lab.OBSERVER)
""")

code(r"""
r = lab.best(lab.VICTIM)
lab.check("the route still arrives — a non-BGPsec network is not cut off",
          r.as_path == [64603, 64601, 64602], str(r))
lab.check("but the path can no longer be verified",
          r.path_state == "invalid", str(r))
lab.check("and it is de-preferred rather than dropped",
          r.best and r.localpref <= r.localpref_base, str(r))
obs = lab.best(lab.OBSERVER)
lab.check("at the far end: origin provable, path not signed at all",
          obs.origin_state == "valid" and not obs.signed, str(obs))
lab.checkpoint("D15")
""")

md(r"""
Look carefully at what AS64605 ends up with. It can still prove *who owns the
prefix* — that is ROV, and it works regardless. It can prove **nothing** about
the path, because the chain was never started.

Note the configuration choice that made this survivable: these routers
de-prefer unverifiable paths rather than dropping them. Had they dropped them,
turning on BGPsec would have disconnected this network from everyone who has
not deployed it — which today is almost everyone. That is not a hypothetical
tuning decision; it is the reason the deployment cannot bootstrap.

## D16. What BGPsec does not claim to stop

One more boundary, and it is worth being precise about because it is often
misunderstood.

Suppose AS64604 receives the real, fully signed route and re-announces it to a
network it should not have — a customer's route leaked to a peer, say, in
violation of a business arrangement. Every signature verifies. The path is
real: those adjacencies exist and each hop genuinely forwarded the route.

BGPsec rates it **valid**, and is right to. A **route leak** is a path that is
cryptographically true and commercially wrong, and BGPsec makes no claim about
commercial relationships. That is a different problem with a different
proposed answer (ASPA), out of scope here.

The lesson worth carrying: BGPsec proves *this route travelled this path*. It
does not prove the route *should* have travelled it.
""")

md(r"""
## Synthesis — Part D

You have now seen the whole arc: two attacks, two defences, and the cost of
the second one.

**Given everything in this lab, why has essentially nobody deployed BGPsec?**

Build the answer from evidence you have rather than from opinion. Useful
threads to pull:

- what Part D showed about a partly-deployed network — who benefits from
  deploying first?
- what you concluded in Part C about what each signature covers, and what that
  implies about the cost of announcing a route to many peers;
- what Part B achieved on its own, and at what cost by comparison;
- and, for the honest version: the fact that this lab runs on two research
  implementations because those are most of the ones that exist.
""")

answer(r"""
Four reinforcing reasons, roughly in order of how binding they are.

**1. The incentives are backwards at the start.** In Part D, the network that
deployed BGPsec got nothing from it: an unsigned route is unverifiable no
matter how carefully you verify. Value appears only when *both* ends of a path
have deployed, so the first mover pays full cost for zero benefit, and the
benefit arrives late and gradually. This is the classic bootstrapping problem
and it is the dominant reason.

**2. You cannot enforce it, so it buys you little even when it works.** Because
unverifiable paths must be accepted (dropping them means disconnection), an
attacker can simply strip the signatures and announce a plain BGP route. A
partly-deployed BGPsec world degrades to a *preference* for signed paths, not
a requirement — and a preference is a much weaker security property than the
protocol's design suggests.

**3. The cost is per-neighbour and unavoidable.** From Part C: a signature
commits to the recipient AS, so it cannot be computed once and reused across
peers. A router announcing a full table to many peers must produce a distinct
signature for each, and verify chains on everything it receives. This is real
CPU and memory in the most performance-sensitive part of a network, on
hardware with long replacement cycles.

**4. ROV already captured most of the practical benefit, far more cheaply.**
Part B stopped a real, common, damaging attack — accidental and malicious
origin hijacks are what actually happens — with no per-message cryptography,
no router upgrades, and an incremental deployment story where deploying helps
you immediately. BGPsec addresses a rarer and more sophisticated attack for
a much higher price. Operators noticed.

**And the state of the implementations.** This lab runs on QuaggaSRx and
GoBGP-SRx because they are two of the five software implementations that exist
at all, and no hardware router implements BGPsec. Of the other three, one
validates incorrectly and one crashes its peers. SIDN Labs' 2025 assessment
concluded all five are "far from being able to support BGPsec in production."
That is not a cause of non-deployment so much as a symptom: implementations
get production-hardened when someone intends to deploy them.

The honest summary: BGPsec is a well-designed answer to a genuine problem,
which asks the internet to pay a large cost up front for a benefit that only
materialises after almost everyone has paid it. Nothing in the protocol is
broken. The economics are.
""")

# ===========================================================================
#  Wrap up
# ===========================================================================

md(r"""
---
---

## Finishing up

`reset()` puts the lab back to Part A — no validation, no attack, no ROA — so
you can run any part again from a clean baseline.
""")

code(r"""
lab.reset()
""")

md(r"""
When you are done for good, tear it down. This frees the containers and the
virtual links; nothing on your machine is left running.
""")

code(r"""
# lab.destroy()
""")

md(r"""
### If you want to keep going

- **Revoke a certificate.** Remove a router's BGPsec certificate from Krill in
  Part C and watch routes that were valid stop verifying, with no change to
  any router.
- **Read a capture yourself.** `lab.capture(node, iface)` writes a pcap you can
  open in Wireshark, which has understood `BGPsec_PATH` since version 3.2.
- **Break something deliberately.** Point a router at the wrong SKI and work
  out, from the router's output alone, what went wrong.
""")

md(r"""
---

## Instructor notes

**Running time.** About 60–75 minutes for a student working through it
attentively. The slow cells are `deploy()` (2–3 min on first run) and
`signature_growth()` (~2 min, four captures with session resets). Part
switches take 45–70s each; the helpers poll, so a cell that seems to hang for
a minute is usually just converging.

**Where students get stuck.**

1. *Preflight fails on the docker group.* Group membership only applies at
   login. They must start a new session, not just `su` or re-source a profile.
2. *A cell reports a stale answer.* Almost always a re-run of an observation
   cell before convergence. `lab.show()` is a snapshot; the `wait_for_*`
   helpers poll. Re-running is safe and idempotent.
3. *Everything is Established but there are no routes.* The validation engine's
   client table has stale entries; `lab.set_part(<current part>)` restarts it
   cleanly. This was common before the srx_server restart was added to
   `set_part.sh` and should now be rare.

**The moment that matters** is B8. If a student is skimming, slow them down
there: have them predict the result before running the cell. The whole
argument for Part C rests on their having believed Part B worked — which is
why B7 is a genuine, satisfying success before B8 undoes it.

**A question that comes up:** "couldn't the attacker just not sign?" Yes — and
that is exactly Part D's point, so it is worth deferring rather than answering
early. In a fully deployed BGPsec world the unsigned route would be rejected;
in the real, partly deployed one it cannot be, and the answer to the question
is the answer to why deployment stalled.

**Grading the synthesis answers.** A1 is answerable from observation alone.
B's second question ("was that a bug?") separates students who followed the
mechanism from those who pattern-matched "validation failed". C's second half
(why the recipient is signed) is the hardest thing in the lab and it is
reasonable for students to need the answer given to them — the useful check is
whether they can then explain what breaks without it.
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
    build(os.path.join(LAB, "bgpsec-lab.ipynb"), include_teacher=False)
    build(os.path.join(LAB, "bgpsec-lab-instructor.ipynb"), include_teacher=True)
