[README](README.md) | [Tasks](Tasks.md) | BGPsec ⮕ | [Task 2](Task-bgpsec-lab.md) | [Lab Exercise](bgpsec_lab_exercise.ipynb)

# Understanding BGPsec — Proving How a Route Actually Traveled

There are two questions BGP itself can never answer:

1. **Is this AS authorized to originate this prefix?**
2. **Is this AS_PATH a truthful account of how the route actually propagated?**

Origin validation answers the *first* question: a prefix holder publishes a signed record of
which AS may originate their address space, and routers drop announcements that contradict
it. But that check looks only at the **rightmost ASN** in the path. An attacker who forges an
AS_PATH so that it *ends in the real owner's ASN* passes origin validation cleanly, while
still pulling the victim's traffic through their own network.

**BGPsec** is the internet's answer to the *second* question. It doesn't change which routes
BGP prefers — it adds a **cryptographic signature from every AS that propagates the route**,
so a receiving router can verify that the AS_PATH really is the sequence of networks the
announcement passed through.

> **Key idea:** BGPsec turns the AS_PATH from an *unverified claim* into a **chain of
> signatures**. Each AS that forwards the route signs a statement naming the prefix, itself,
> and the neighbor it is sending to. An attacker can still *write down* any path they like,
> but they cannot produce the signatures of ASes whose private keys they do not hold — so a
> fabricated path no longer verifies.

Like origin validation, BGPsec is built on the **RPKI** trust hierarchy. The same Regional
Internet Registries (ARIN, RIPE NCC, APNIC, LACNIC, AFRINIC) that certify address space also
anchor certificates for **ASNs**, so a signature made by AS64500 can be traced back to a
trusted root as proof that it really came from AS64500.

---

### Router Certificates and Keys

Before an AS can sign anything, it needs a key pair that is verifiably bound to its ASN. In
RPKI this is a **router certificate** (also called a BGPsec router certificate): an RPKI
certificate whose contents assert *"this public key belongs to a router speaking for
AS64500."*

```
  ┌────────────────────────────────────────────────────────────┐
  │  BGPsec Router Certificate                                 │
  │    ASN:          AS64500        ← whose router this is     │
  │    Public key:   <EC P-256 key> ← used to verify its sigs  │
  │    SKI:          <20-byte id>   ← names this exact key     │
  │                                                            │
  │    (issued under the RPKI cert chain that proves the        │
  │     holder was actually allocated AS64500)                  │
  └────────────────────────────────────────────────────────────┘
```

- **ASN** — the autonomous system this key is allowed to sign on behalf of.
- **Public key** — what every other router uses to *check* signatures from this AS.
- **SKI (Subject Key Identifier)** — a short identifier carried in the BGP update so the
  receiver knows *which* key to fetch, since an AS may run many routers with many keys.

The **private key** never leaves the router (or the operator's signing infrastructure). This
is the whole security property: an attacker can copy a signature they have seen, but they
cannot *create a new one* for a path that never existed, because they don't have the key.

---

### The BGPsec_PATH Attribute

A BGPsec-speaking router does not send the ordinary AS_PATH attribute. It sends a
**BGPsec_PATH** attribute, which carries the same sequence of ASes *plus* a signature from
each of them. Conceptually it is two parallel lists:

```
  BGPsec_PATH  for  203.0.113.0/24

  Secure_Path (who carried it)     Signature_Block (proof from each)
  ────────────────────────────     ──────────────────────────────────────
   AS64502   (most recent)          Sig by AS64502's key  ──┐
   AS64501                          Sig by AS64501's key    │  each signature
   AS64500   (origin)               Sig by AS64500's key  ──┘  covers the one below
```

Each entry in the **Secure_Path** records one AS that propagated the route. Each entry in the
**Signature_Block** is that AS's signature, made with the private key matching its router
certificate.

The signatures are *nested*, not independent. When an AS signs, it signs over:

- the **prefix** being announced,
- its **own** Secure_Path entry,
- the **ASN it is sending the route to** (the target neighbor), and
- **the signature it received from the previous AS**.

That last two items are what make the chain rigid:

- Including the **previous signature** means the signatures form a linked chain. You cannot
  remove an AS from the middle, or reorder the path, without invalidating everything signed
  above it.
- Including the **target ASN** ("forward signing") means a signature is only valid for the
  specific neighbor it was sent to. A peer cannot take a route it legitimately received and
  replay it as though it had been sent to someone else, or shorten the path by splicing.

---

### BGPsec Path Validation

Path validation is the act of *checking* that chain. A receiving router walks the
BGPsec_PATH from the origin outward and, for each AS in it, fetches that AS's router
certificate (by SKI) from the RPKI and verifies the signature. The outcome is one of two
states:

```
  For a BGPsec update carrying prefix P and a BGPsec_PATH:

  ┌───────────┬─────────────────────────────────────────────────────────────┐
  │ VALID     │ Every signature in the block verifies, every signing key     │
  │           │ traces to a valid RPKI router cert for the ASN that claims   │
  │           │ it, each signature names the correct target neighbor, AND    │
  │           │ the origin passes origin validation.                         │
  │           │                        → the path is proven authentic        │
  ├───────────┼─────────────────────────────────────────────────────────────┤
  │ NOT VALID │ Any signature fails, any certificate is missing/expired/     │
  │           │ revoked, the path is malformed, or the origin is not         │
  │           │ authorized.          → the path claim is NOT proven          │
  └───────────┴─────────────────────────────────────────────────────────────┘
```

Note there is no third "unknown" state as there is in origin validation. A route that arrives
as plain BGP simply **has no BGPsec_PATH to check** — it isn't "Not Valid," it is *unsigned*,
and is handled by ordinary policy.

As with origin validation, BGPsec only *labels* a route; the operator's **routing policy**
decides what happens:

- **Valid** → accept, and prefer it over an unsigned route for the same prefix.
- **Not Valid** → treat as untrustworthy. Depending on policy this means depreference or
  outright rejection. (During partial deployment, most operators *depreference* rather than
  drop, so a certificate hiccup doesn't black-hole a legitimate destination.)
- **Unsigned** (plain BGP) → accept, but rank below Valid — the same pragmatic compromise
  that keeps the not-yet-deployed majority of the internet reachable.

> **Key idea:** BGPsec doesn't ask *whether a path looks plausible.* It asks whether every AS
> named in the path actually signed for it. A path nobody signed is a path nobody vouched
> for — and forging that vouching requires private keys the attacker does not have.

---

### How BGPsec stops AS_PATH Manipulation

Recall the interception attack: **AS64500** legitimately originates `203.0.113.0/24`, and
attacker **AS66000** announces the same prefix with a *forged* AS_PATH that ends in AS64500 —
so the route looks like it traces back to the true origin, while traffic actually detours
through the attacker.

Under plain BGP, and even under origin validation alone, that route passes: the rightmost ASN
is the authorized origin, and nothing checks the rest.

Under BGPsec, the attacker has to produce a *signature chain*, not just a list of numbers:

```
  What the attacker wants to send:   203.0.113.0/24   path = [66000, 64500]

  Receiver's verification walk:
  ──────────────────────────────────────────────────────────────────────────────
   AS64500's entry   needs a signature by AS64500's private key
                     over (prefix, AS64500, target = AS66000, ...)
                     → attacker does NOT hold AS64500's key
                     → cannot fabricate it                       ✗ FAILS

   Result: NOT VALID → route rejected / depreferenced
```

The attacker has three ways to try, and all of them fail:

1. **Invent the origin's signature.** Requires AS64500's private key. They don't have it.
2. **Replay a real signature from AS64500.** Real signatures name a *target neighbor* and
   are chained to a specific position. A signature AS64500 made for its actual upstream does
   not verify when presented as if it had been sent to AS66000.
3. **Delete ASes to shorten the path** (making it look more attractive to best-path logic).
   Each signature covers the one beneath it, so removing a link breaks every signature above
   it.

The attack's core trick — *making a false path indistinguishable from a real one* — stops
working, because a real path now carries proof the attacker cannot manufacture.

---

### How BGPsec relates to origin validation

BGPsec **includes** origin validation rather than replacing it. A BGPsec-Valid route must
*also* have an authorized origin — the origin AS's signature proves the announcement really
came from that AS, but only the prefix holder's signed origin record proves that AS was
allowed to announce that address space in the first place.

```
  Question                                   Answered by
  ─────────────────────────────────────────  ──────────────────────────────────
  May this AS originate this prefix?         Origin validation (signed ROAs)
  Did the route really travel this path?     BGPsec (signed BGPsec_PATH)
```

Neither is sufficient alone. Origin validation with no path protection lets forged-path
interception through as Valid. Path signatures with no origin record would faithfully prove
that a *hijacker* really did announce the prefix — which is true, and useless.

---

### What BGPsec does *not* do

BGPsec proves that a path was **propagated as claimed**. It does not prove that propagating
it was **allowed**.

- **Route leaks are not prevented.** If a customer AS receives a route from one upstream and
  re-announces it to another upstream — violating normal valley-free business policy — every
  signature in the chain is perfectly genuine. The path is *authentic* and *wrong*. BGPsec
  says nothing about whether an AS *should* have passed the route along. (This gap is what
  mechanisms like **ASPA**, which record an AS's authorized upstream providers, are meant to
  address.)
- **It does not protect the data plane.** BGPsec secures routing *announcements*. It gives no
  guarantee that packets actually follow the advertised path once forwarding begins.
- **It offers no protection along unsigned segments.** Signatures only cover the portion of
  the path where every AS speaks BGPsec.

That last point is the practical crux of deployment.

---

### Why is deployment hard?

Everything above says BGPsec *works*: it closes the attack that origin validation cannot, and
the cryptography behind it is ordinary, well-understood signature verification. And yet
origin validation is deployed across a large and growing share of the internet, while BGPsec
is almost nowhere in production.

Before reading on, work out **why** for yourself.

#### Task: Predict the obstacles

Think through what actually changes for a network operator who turns BGPsec on tomorrow.
Consider each of these angles and write down what you think goes wrong:

- **The first adopter.** You enable BGPsec. None of your neighbors have. What protection do
  you actually gain today?
- **The unsigned majority.** Most of the internet still sends plain BGP updates that you
  *must* keep accepting. What does an attacker do with that fact?
- **The router's workload.** A plain BGP update carries an AS_PATH that is a few bytes to
  copy. A BGPsec update carries one signature per AS hop. What has to happen on a router
  holding a full internet routing table — roughly a million prefixes — and what happens
  during a convergence storm?
- **The keys.** Signing requires private keys on (or behind) every border router in your
  network, and certificates that other networks fetch to verify you. What ongoing work does
  that create, and what breaks when it goes wrong?

Fill in your predictions:

| Angle | What you think the obstacle is |
| --- | --- |
| **First adopter** | ______________________________ |
| **Unsigned majority** | ______________________________ |
| **Router workload** | ______________________________ |
| **Key management** | ______________________________ |

Then ask yourself the summarizing question: **origin validation and BGPsec are both signed,
RPKI-rooted mechanisms — so what is different about BGPsec that made one of them easy to
deploy and the other one hard?**

...

---

#### The reasons

BGPsec's guarantees are strong, but they come with real costs that have kept adoption far
behind origin validation.

**Contiguity.** Protection requires an *unbroken* run of BGPsec speakers. The moment a route
crosses an AS that doesn't support it, the BGPsec_PATH is stripped and the update continues
as ordinary BGP:

```
  AS64500 ──sig──► AS64501 ──sig──► AS64502 ──── AS64503 ──── AS64504
   (BGPsec)         (BGPsec)         (BGPsec)     (plain BGP)   (BGPsec)
                                                       │
                                        signatures are dropped here;
                                        AS64504 receives an ordinary,
                                        unverifiable AS_PATH
```

This creates a hard bootstrapping problem: early adopters get almost no benefit until their
*neighbors* adopt too.

**Downgrade.** Because unsigned routes must still be accepted, an attacker can often simply
**not** speak BGPsec and announce a plain-BGP forgery. Whether that succeeds depends entirely
on how aggressively receiving networks prefer signed routes over unsigned ones — which,
today, is not very.

**Cost.** Every BGPsec update requires a signature *per AS hop*, and every receiver must
verify all of them. Compared with a plain BGP update — where the AS_PATH is a few bytes to
copy — this is dramatically more CPU and memory, especially during a full table load or a
convergence storm. It also inflates update size, and it removes optimizations plain BGP
relies on: signed updates cannot be aggregated across prefixes, so a router must send one
signed update per prefix.

**Key management.** Router certificates must be issued, distributed, rotated, and revoked
across an operator's entire edge. That is ongoing operational work with no equivalent in
plain BGP.

**The underlying asymmetry.** Compare this with origin validation, and the answer to the
summarizing question comes into focus: publishing a ROA is a **unilateral** act. A prefix
holder signs a record about *their own* address space, and any single network that starts
validating gets immediate benefit — no coordination with neighbors required. BGPsec is
inherently **collective**: a signature chain is only as good as the ASes that participate in
it, so the value to any one operator depends on decisions made by everyone else along the
path. Cheap and unilateral got deployed; expensive and collective did not — despite BGPsec
closing the more subtle attack.

---

### Check your understanding

1. In one sentence each, what does a **router certificate** bind together, and what does the
   **BGPsec_PATH** attribute carry beyond an ordinary AS_PATH?
2. Why does each AS sign over the **ASN it is sending the route to**? What attack would be
   possible if it signed only over the prefix and its own ASN?
3. An attacker announces a prefix with a forged path ending in the real owner's ASN. Explain
   why this passes origin validation but fails BGPsec path validation.
4. A route leak is propagated by ASes that all sign correctly. What does BGPsec report, and
   why is that answer both correct and unhelpful?
5. Why does a single non-BGPsec AS in the middle of a path undo the protection for everyone
   downstream — and why does that make early adoption unattractive?

---

### BGPsec resources
- [RFC 8205 — BGPsec Protocol Specification](https://www.rfc-editor.org/rfc/rfc8205.html) — the core BGPsec specification.
- [RFC 8206 — BGPsec Considerations for AS Migration](https://www.rfc-editor.org/rfc/rfc8206.html) — how BGPsec interacts with real-world ASN changes.
- [RFC 8208 — BGPsec Algorithms, Key Formats, and Signature Formats](https://www.rfc-editor.org/rfc/rfc8208.html) — the cryptography BGPsec uses.
- [RFC 8209 — A Profile for BGPsec Router Certificates](https://www.rfc-editor.org/rfc/rfc8209.html) — how router certs are issued under RPKI.
- [RFC 8374 — BGPsec Design Choices and Summary of Supporting Discussions](https://www.rfc-editor.org/rfc/rfc8374.html) — why BGPsec was designed the way it was.
- [NIST BGP Secure Routing Extension (BRITE / SRx)](https://www.nist.gov/programs-projects/robust-inter-domain-routing) — reference implementations and testbeds for BGPsec.

[README](README.md) | [Tasks](Tasks.md) | BGPsec ⮕ | [Task 2](Task-bgpsec-lab.md) | [Lab Exercise](bgpsec_lab_exercise.ipynb)
