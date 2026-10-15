# The BGPsec lab, explained

A complete walkthrough of what every part of this repository is and what it
does. Read `lab/README.md` first if you just want to run the thing; this is
the document for changing it, debugging it, or understanding why it is shaped
the way it is.

**Contents**

1. [What this project is](#1-what-this-project-is)
2. [Repository layout](#2-repository-layout)
3. [The running system](#3-the-running-system)
4. [Addressing](#4-addressing)
5. [Startup ordering](#5-startup-ordering)
6. [How validation actually flows](#6-how-validation-actually-flows)
7. [Key material](#7-key-material)
8. [The four curriculum states](#8-the-four-curriculum-states)
9. [What a part switch does](#9-what-a-part-switch-does)
10. [The images](#10-the-images)
11. [File-by-file](#11-file-by-file)
12. [labkit.py reference](#12-labkitpy-reference)
13. [Constraints that shaped the design](#13-constraints-that-shaped-the-design)
14. [Debugging recipes](#14-debugging-recipes)

---

## 1. What this project is

A teaching lab. Students run a small internet of six autonomous systems,
attack it twice, defend it twice, and finish by understanding why the second
defence is essentially undeployed in the real world.

The deliverable is one Jupyter notebook, `lab/bgpsec-lab.ipynb`. Everything
else exists to make that notebook run.

The pedagogical order is deliberate and is the whole design: **break it first,
then fix it in the order history did.** Each protection is introduced only
after students have watched the attack it stops succeed against them. The
pivot is Part B → C, where route origin validation is introduced, appears to
solve hijacking, and is then defeated in front of them by a forged path that
RPKI rates `Valid`. That moment only lands because they ran the ROV exercise
first and believed it worked.

Two technologies are in scope: **RPKI/ROV** (which authorises *who may
originate* a prefix) and **BGPsec** (which authenticates *the path a route
took*). ASPA is out of scope.

---

## 2. Repository layout

```
caida/
├── bgpsec-lab-plan.md      the original design document
├── quick-setup.sh          host preparation (Docker, containerlab, groups)
├── REFERENCE.md            this file
├── bgpsec-testbed/         vendored clone of SIDN/bgpsec-testbed, unmodified
└── lab/                    everything built for this project
    ├── bgpsec-lab.ipynb            THE DELIVERABLE
    ├── bgpsec-lab-instructor.ipynb same + model answers and teaching notes
    ├── labkit.py                   the notebook's entire interface to the lab
    ├── reset.sh                    return the lab to a clean state
    ├── build-images.sh             build all images from source
    ├── README.md                   quick orientation
    ├── IMAGES.md                   image provenance and what the overlays add
    ├── PHASE5.md                   verification record for the notebook phase
    ├── configs/                    lab-owned service configs
    ├── overlay/                    thin Dockerfiles over the upstream images
    ├── tools/                      generation, capture, testing
    ├── dist/                       the distributable image bundle
    ├── phase1/                     two-router topology + Phase 1/2 records
    ├── phase3/                     four-AS topology + Phase 3 record
    └── phase4/                     THE LAB TOPOLOGY + configs + keys
```

### The vendored testbed

`bgpsec-testbed/` is a clone of [SIDN Labs' bgpsec-testbed][sidn] at commit
`c90b222`, **deliberately unmodified**. It supplies the hard parts: working
Dockerfiles for the routers, a certificate generation script, and a working
RPKI trust chain. This project ports it from `docker-compose` on a flat bridge
to Containerlab on point-to-point links.

Nothing in `lab/` writes to it. Where a testbed config needed changing, a
lab-owned copy lives in `lab/configs/` and is bound over the top. This matters:
you can always diff against upstream to see what this project actually changed.

### The phase directories

`phase1/`, `phase3/` and `phase4/` are the successive topologies built while
developing the lab, each with a `PHASE*.md` recording what was verified and
what broke. **Only `phase4/` is the lab.** The others are kept because their
records document behaviours — of QuaggaSRx, SRx-server and containerlab — that
constrain what the curriculum can do, and rediscovering them is expensive.

| Phase | What it established |
|---|---|
| 1 | Two routers, signed UPDATE validates end to end |
| 2 | RPKI plane: ROA lifecycle CA → validator → RTR → router |
| 3 | Four ASes on point-to-point links; signature count == hop count |
| 4 | Attacker AS, four curriculum states, all attacks and defences |
| 5 | `labkit.py` and the notebook |

---

## 3. The running system

Twelve containers. Ten stay up; two are one-shots that do a job and exit.

### The RPKI plane

These run on the management network only. They are the machinery that makes
"is this route authorised?" a question with an answer.

**`rsyncd`** — `vimagick/rsyncd`, 10.0.0.12
The **publication point**. A plain rsync server exporting two directories:
`repo` (everything the CA publishes — certificates, ROAs, manifests, CRLs) and
`ta` (the trust anchor). In the real RPKI these are run by the RIRs. Serves
port 873.

**`krill`** — `nlnetlabs/krill:v0.14.5`, 10.0.0.10
The **certificate authority**. Holds the lab's self-signed trust anchor and
issues two kinds of object: ROAs (authorising an AS to originate a prefix) and
BGPsec router certificates (binding a router's public key to its AS number).
HTTP API on port 3000. Writes published objects into the shared `rsync_repo`
directory, which `rsyncd` then serves.

> **The pin to v0.14.5 is required, not cosmetic.** Krill 0.15 removed the
> `-t/-c/-s` krillc flags that the testbed's `sign_csr.sh` uses. On `latest`,
> `krillc` crash-loops with `unexpected argument '-t'`, never signs a CSR, and
> the deploy hangs with an empty trust anchor directory.

**`krillc`** — same image, 10.0.0.9, **one-shot**
Runs `sign_csr.sh`, which walks the key vault's `ski-list.txt` and submits
every router CSR to Krill, then copies each issued certificate back into the
vault and exits. Adding an AS to the lab needs no change here — it reads the
vault.

**`tal_share`** — `bgpsec/tal-share:local`, 10.0.0.11, **one-shot**
Fetches Krill's trust anchor (`ta.cer` and `ta.tal`) over HTTP and drops them
into the shared `rsync_ta` directory so Routinator can bootstrap trust. Two
`curl` calls, then exits.

**`routinator`** — `nlnetlabs/routinator:v0.15.2`, 10.0.0.14
The **relying party / validator**. Fetches everything from the publication
point, verifies signatures and certificate chains, and turns valid objects
into two flat lists: **VRPs** (prefix, max-length, ASN) from ROAs, and
**router keys** (ASN, SKI, public key) from BGPsec certificates. Serves them
to routers over **RTR on port 3323**, with HTTP status on 8323 and Prometheus
metrics on 9556.

**`srx_server`** — `bgpsec/srx-server:local`, 10.0.0.15
NIST's **validation engine**. The QuaggaSRx routers do not implement RTR or
signature verification themselves; they delegate both to this. It holds one
RTR session to Routinator, caches VRPs and router keys, and answers per-update
validation queries from routers over its proxy protocol on **port 17900**. A
diagnostic console listens on **17901**.

### The routers

**`as64601`** (10.0.0.7), **`as64602`** (10.0.0.2), **`as64603`** (10.0.0.3),
**`as64604`** (10.0.0.4) — `bgpsec/quaggasrx:local`
QuaggaSRx 0.6.0.4. AS64602 originates `10.64.2.0/24`; the rest are transit.
Each connects to `srx_server` as a proxy client. Driven through bgpd's VTY on
port 2605 (there is no `vtysh` in the image).

**AS64604 is the victim**: it peers with the attacker, so it is where every
attack is judged and where the notebook does most of its observing. It is
QuaggaSRx because QuaggaSRx is the only implementation here with policy that
can *act* on a BGPsec result.

**`as64605`** (10.0.0.5) — `bgpsec/gobgpsrx:local`
GoBGP-SRx 2.14.0, the **observer** at the far end. It works differently from
the others in two ways that matter:

- it does **not** use `srx_server` — it verifies signatures locally through
  srx-crypto-api against the shared key vault;
- it runs its **own** RTR client straight to Routinator for origin validation.

Its status column reads `<origin>,<bgpsec>`, e.g. `V,V` or `I,N`.

> The plan's implementation table says GoBGP-SRx has "no RTR integration".
> That is true of *router key* PDUs — it reads keys from the local vault — but
> not of VRPs. It keeps upstream GoBGP's RTR client and does full ROV.

**`as64666`** (10.0.0.6) — `bgpsec/quaggasrx:local`
The **attacker**. Same image as everyone else, its own Krill-issued router
certificate, its own SRx proxy session. It has no privilege of any kind: every
attack in Parts A–C is mounted with nothing but the ability to send a BGP
UPDATE. Its config defines a `forge-origin` route-map that is not attached
until an exercise attaches it.

---

## 4. Addressing

Two planes, deliberately separated.

**Management network** — `10.0.0.0/24`, bridge `br-bgp`.
Carries SRx proxy traffic, RTR, rsync, HTTP, and host access. **No BGP
peerings ride this network.**

| Node | Address | | Node | Address |
|---|---|---|---|---|
| gateway | 10.0.0.1 | | as64605 | 10.0.0.5 |
| as64602 | 10.0.0.2 | | as64666 | 10.0.0.6 |
| as64603 | 10.0.0.3 | | as64601 | 10.0.0.7 |
| as64604 | 10.0.0.4 | | krillc | 10.0.0.9 |
| krill | 10.0.0.10 | | tal_share | 10.0.0.11 |
| rsyncd | 10.0.0.12 | | routinator | 10.0.0.14 |
| srx_server | 10.0.0.15 | | | |

> **10.0.0.1 is the bridge's own gateway address.** AS64601 uses .7 because
> binding .1 fails the node with "Address already in use". If you add a
> router, do not reach for .1.

**Data plane** — one `/24` per link, dedicated veth pairs. Host octet is the
AS's last digit.

| Link | Addresses |
|---|---|
| as64602:eth1 ↔ as64601:eth1 | 10.21.0.2 ↔ 10.21.0.1 |
| as64601:eth2 ↔ as64603:eth1 | 10.13.0.1 ↔ 10.13.0.3 |
| as64603:eth2 ↔ as64604:eth1 | 10.34.0.3 ↔ 10.34.0.4 |
| as64604:eth2 ↔ as64605:eth1 | 10.45.0.4 ↔ 10.45.0.5 |
| as64604:eth3 ↔ as64666:eth1 | 10.46.0.4 ↔ 10.46.0.6 |

**Point-to-point links are the entire argument for using Containerlab here.**
The upstream testbed puts every router on one shared bridge, where the BGPsec
signature block cannot be observed hop by hop. On dedicated links you can
capture a single inter-AS link and watch the signature count grow by one at
each hop — which is exercise C11 and was Phase 3's exit criterion.

Addresses are applied by containerlab `exec:` statements at node creation, not
by the router configs.

### Why the topology has five legitimate ASes

The plan called for four. It needs five, and the reason is measured rather
than aesthetic.

The attacker's forged path is always exactly two hops (`64666 64602`), so it
only wins where the real path is *longer* than two. In a four-AS chain the
real path reaches AS64604 in two hops as well — the two tie, the tie breaks on
router-id, and the attack fails for a reason that teaches nothing about
routing security. AS64601 makes the real path three hops, so the forgery wins
on merit.

---

## 5. Startup ordering

Containerlab `stages` / `wait-for` enforces this chain. Each dependency is
real; the RPKI plane cannot be started in parallel.

```
rsyncd (created)
   └─> krill (healthy: HTTP /health responds)
          └─> krillc (exit 0: every router CSR signed)
                 ├─> tal_share (exit 0: trust anchor fetched)
                 └─> routinator (healthy, after BOTH krillc and tal_share exit)
                        └─> srx_server (created)
                               └─> all six routers
```

Reading it as a sentence: the publication point must exist before the CA can
publish to it; the CA must be answering before certificates can be signed; the
trust anchor must exist before the validator can verify anything; the
validator must be serving before the validation engine can populate its cache;
and the routers must not come up before something can answer their questions.

> **One-shots need `restart-policy: "no"`.** Docker's default restarts a
> container even after a clean exit, so `wait-for: {stage: exit}` never fires
> and the deploy hangs forever. This cost a day in Phase 1.

---

## 6. How validation actually flows

There are two independent paths, and knowing which is which is essential to
debugging.

**QuaggaSRx routers (AS64601–4, AS64666):**

```
Krill ──publishes──> rsync_repo ──rsync──> Routinator
                                              │ RTR :3323
                                              │ (VRPs + Router Key PDUs)
                                              v
                                          srx_server
                                              │ SRx proxy :17900
                                              │ (per-update queries)
                                              v
                                        QuaggaSRx bgpd
```

The router sends each received update to `srx_server` and gets back an origin
result, a path result, and an ASPA result. It then applies local policy
(`srx policy ...`) to decide what to do with those results.

**GoBGP-SRx (AS64605):**

```
Routinator ──RTR :3323──> gobgpd (own RTR client, VRPs only)
key vault  ──local file──> srx-crypto-api (signature verification)
```

No `srx_server` involvement at all.

**Consequences worth internalising:**

- If `srx_server` is unhappy, the four QuaggaSRx routers lose *both* origin and
  path validation, and AS64605 is unaffected. That asymmetry is a useful
  diagnostic signal.
- Origin validation depends on the whole chain up to Routinator. Signature
  verification on AS64605 depends only on the local vault.
- Propagation of a CA-side change to a router takes roughly 25 seconds:
  Routinator's `refresh` is set to 30s (upstream default is 600s, which is
  unusable for teaching), and the RTR leg is notification-driven, so it is
  near-instant once Routinator has the data.

---

## 7. Key material

`lab/phase4/keys/` is the lab-owned key vault, bind-mounted read-write into
every router and into Krill and krillc.

Layout follows what NIST-BGP-SRx expects — the SKI split across directory
levels:

```
keys/
├── ski-list.txt        ASN -> SKI, public
├── priv-ski-list.txt   ASN -> SKI, private half
├── ca.pem, ca.cert     the lab CA used to self-sign placeholder certs
└── <SKI[0:2]>/<SKI[2:6]>/<SKI[6:]>.{der,csr,cert}
        .der   the private key
        .csr   the certificate signing request
        .cert  the certificate (Krill overwrites this at deploy)
```

A **SKI** (Subject Key Identifier) is the SHA-1 of the public key, and is how
a signature says "here is which key to check me against". The same twenty
bytes appear in three places, and exercise C11 has students confirm all three
agree:

1. `ski-list.txt` in the vault (on disk),
2. a Router Key PDU served by Routinator over RTR (on the management wire),
3. a signature segment inside a `BGPsec_PATH` attribute (on the data wire).

`srxcryptoapi.conf` points the crypto library at the vault and at both list
files — that is how a router knows its own private key and everyone else's
public keys.

The lab has six keys: one per AS including the attacker. The vault itself is
not committed — a deploy rewrites its certificates and chowns the private keys
to root — but the private keys are: AS64602–64605 come from the vendored
testbed (`bgpsec-testbed/key_setup/bird_testbed_keys/bgpsec-private-keys/`),
AS64601 and AS64666 from `lab/router_keys/`, all DER EC P-256 files named
`<asn>.<SKI>.key`. `tools/build_vault.sh` derives everything else in the
layout above from those files — CSRs, placeholder certs, both SKI lists — and
checks each file's name against its key. `labkit.deploy()` and the Codespace
bootstrap run it, so a fresh clone needs no manual step. Same keys in, same
SKIs out, which is what keeps the generated configs valid on every machine.

Adding an AS means `tools/add_router_key.sh` for a throwaway key, or — to keep
it across machines — a `<asn>.<SKI>.key` in `lab/router_keys/` and a
`build_vault.sh --force`; krillc signs any new CSR automatically on the next
deploy.

---

## 8. The four curriculum states

The same six routers run four different configurations. `labkit.set_part()`
switches between them.

| Part | Origin validation | BGPsec | The lesson |
|---|---|---|---|
| **a** | off | off | Both attacks succeed. Nothing is verified. |
| **b** | on, drops Invalid | off | Hijack stopped; **forged path rated Valid and wins** |
| **c** | on | on, drops Invalid | Forgery stopped; revocation kills a route |
| **d** | on | on, except AS64602 | Partial deployment: unverifiable but not cut off |

All twenty-four config files (six routers × four parts) are **generated** from
one table in `tools/gen_configs.py`. Writing them by hand would be the same
SKIs, neighbours and policy lines copied twenty-four times, one edit away from
a lab that teaches the wrong thing because a stale config is bound.

Three details in the generated configs are load-bearing:

- **A session negotiates BGPsec only if both ends have it enabled.** That is
  what makes part `d` work — turning AS64602 off automatically drops BGPsec
  from its session without touching its neighbour's entry.
- **Part `d` de-prefers invalid paths instead of dropping them.** An unsigned
  route arriving on a BGPsec session scores *invalid*, not "unknown", so
  dropping invalids in part `d` would disconnect every AS that has not
  deployed BGPsec — which is nearly all of them. De-preferring is what a real
  operator would do, and it is the whole answer to Part D's synthesis question.
- **`no srx policy origin ignore undefined` is set explicitly.** QuaggaSRx
  defaults to dropping routes it has no validation answer for, so a hiccup in
  `srx_server` silently becomes "this router has no internet". Failing open on
  validator loss is both safer for the lab and what production deployments
  choose.

---

## 9. What a part switch does

`tools/set_part.sh <phase4-dir> <part>`:

1. copies `configs/<part>/*.conf` over `configs/active/`, which is what the
   topology binds into the containers;
2. restarts **`srx_server` first, alone**, then waits 4 seconds;
3. restarts each router's daemon in turn, staggered 2 seconds apart;
4. restarts `gobgpd` on the observer.

RPKI state — ROAs in Krill, issued certificates — is deliberately untouched, so
a ROA issued in Part B is still there in Part C. The narrative depends on that.

A restart also drops any attack the attacker was announcing, because attacks
are runtime VTY commands rather than config. That is why each part explicitly
re-runs them ("replay attack 2").

**Why a restart at all, and why in that order:**

- BGPsec cannot be toggled on a live session. Removing `neighbor X bgpsec both`
  from both ends and clearing the session leaves bgpd still emitting
  BGPsec-shaped UPDATEs; the peer answers `Missing well-known attribute 3` and
  the session sits in Idle forever. The setting only takes effect at daemon
  start.
- `docker restart` would restart the daemon, but **containerlab veths do not
  survive container recreation**. The node comes back with only `eth0`, no
  error is reported anywhere, and the lab looks deployed while being entirely
  broken. Hence the supervisor as PID 1 in the images, and `pkill` instead.
- `srx_server` goes first because its client table is keyed by proxy ID and
  outlives the routers that registered. A router restarting into its own stale
  entry never completes the handshake, so every validation returns `undefined`.
  Restarting it first gives everyone a clean table.
- The stagger exists because five simultaneous proxy handshakes was enough to
  make one lose the race even against a clean table.

---

## 10. The images

Built by `lab/build-images.sh`. Each daemon image is built twice: once from
the pristine testbed Dockerfile (`:upstream`), then through a thin overlay
(`:local`). **The lab only ever runs `:local`.**

| Tag | Size | Contents |
|---|---|---|
| `bgpsec/quaggasrx:local` | 244 MB | QuaggaSRx 0.6.0.4 + srx-crypto-api |
| `bgpsec/gobgpsrx:local` | 262 MB | GoBGP-SRx 2.14.0 + srx-crypto-api |
| `bgpsec/srx-server:local` | 215 MB | SRx-Server 0.6.2.1 |
| `bgpsec/tal-share:local` | 18.9 MB | Alpine + `get_ta.sh` |

The overlays add exactly two things:

**Capture tooling** — `tcpdump`, `iproute2`, `iputils-ping`, `procps`. This is
not a convenience: it makes `docker exec <node> tcpdump` the capture method
instead of `ip netns exec`, which would need `sudo` and would hang a notebook
cell on an invisible password prompt.

**A supervisor as PID 1** (`overlay/run-daemon.sh`) — a `while true` loop
around the daemon, so `pkill -x bgpd` restarts it against an edited config
without recreating the container. The 1-second floor stops a config syntax
error from spinning the CPU.

There are **no prebuilt images on Docker Hub** for any of the NIST components
(`nist/bgp-srx` 404s). Everything compiles from source, which is slow, so the
four `:local` images ship as `dist/bgpsec-lab-images.tar.gz` (275 MB).
`nlnetlabs/krill`, `nlnetlabs/routinator` and `vimagick/rsyncd` are pulled from
Docker Hub and are not in the bundle.

> The upstream Dockerfiles `git clone` the NIST sources without a ref, so a
> rebuild picks up whatever is on master that day. The SHAs that went into the
> current bundle are recorded in `IMAGES.md`.

---

## 11. File-by-file

### Root

**`bgpsec-lab-plan.md`** — the original design document: the reality check on
BGPsec's deployment status, the interop matrix that explains why only two
implementations are used, the phase plan, and the curriculum outline. Still
the best statement of *why* the lab is shaped this way. Where the built lab
deviates, the phase records say so and why.

**`quick-setup.sh`** — host preparation. Installs Docker (pinned 27.5.1, newer
on some distros) and containerlab, creates the `docker` and `clab_admins`
groups and adds the user to both, and installs some shell conveniences.
Containerlab installs setuid root, which together with `docker` group
membership is what makes the whole lab runnable without `sudo`.

### `lab/` — top level

**`bgpsec-lab.ipynb`** — the deliverable. 88 cells: preflight, deploy, Parts
A–D, synthesis questions, teardown. Each exercise is markdown framing → action
cell → observation cell → assertion cell.

**`bgpsec-lab-instructor.ipynb`** — 93 cells: the same content plus model
answers to all four synthesis questions and a section of teaching notes
(timings, where students get stuck, which moment to slow down for).

Both are **generated** by `tools/build_notebook.py`. Editing the `.ipynb`
directly lets the two drift, and a stale instructor copy is worse than none
because it is trusted.

**`labkit.py`** — everything the notebook calls. See §12.

**`reset.sh`** — return the lab to a clean state without redeploying.
`./reset.sh [a|b|c|d]` clears attacks and ROAs and switches part; `--hard`
destroys and redeploys, rebuilding the RPKI trust chain.

**`build-images.sh`** — builds all four images from source, `:upstream` then
`:local`.

**`README.md`** — quick orientation and how to run.
**`IMAGES.md`** — image provenance, source commits, what the overlays add, and
the bundle checksum.
**`PHASE5.md`** — verification record for the notebook phase.

### `lab/configs/` — lab-owned service configs

**`routinator.conf`** — upstream's config with one change: `refresh = 30`.
The 600-second default means a ROA issued in Krill takes up to ten minutes to
reach the routers, which is unusable for an interactive exercise. Also sets
`enable-bgpsec = true`, `no-rir-tals = true` (this lab trusts only its own TA)
and `extra-tals-dir` pointing at the fetched trust anchor.

**`srx_server.conf`** — upstream's config with the `mapping` block extended
from two clients to all five QuaggaSRx routers. Pre-configured proxy IDs get
reserved slots; dynamically allocated ones survive the router that made them
and then block that router's own reconnect at the next part switch.

### `lab/overlay/` — image overlays

**`run-daemon.sh`** — the PID 1 supervisor. Its header comment is the full
explanation of why it exists.
**`quaggasrx.Dockerfile`**, **`gobgpsrx.Dockerfile`**, **`srx-server.Dockerfile`**
— add capture tooling and the supervisor over the `:upstream` tags.

### `lab/tools/`

**`gen_configs.py`** — generates all twenty-four router configs from one
topology table. The single source of truth for who peers with whom, who signs,
and what policy each part applies. Reads SKIs from the vault rather than
hardcoding them, so regenerating keys cannot silently leave configs pointing at
dead ones. **Edit this, not the generated configs.**

**`set_part.sh`** — switches curriculum state. See §9.

**`build_vault.sh`** — builds `phase4/keys/` from the tracked private keys
(the vendored testbed's four plus `router_keys/`): layout, CSRs, placeholder
certs, SKI lists. Idempotent; `--force` rebuilds, moving the old vault aside.
Run by `labkit.deploy()` and the Codespace bootstrap. See §7.

**`add_router_key.sh`** — generates an EC P-256 key, CSR and placeholder
certificate for a new ASN and files them into the vault in NIST layout.
Extracted from the testbed's `create_certificates.sh` with the same openssl
invocations, minus the parts that rewrite upstream config files.

**`vty.sh`** — drives a QuaggaSRx VTY from the shell without `vtysh` or
`sudo`. The shell prototype of what `labkit.vty()` does; useful when you are
not in a notebook.

**`rtr_query.py`** — a minimal RFC 8210 RTR client. Sends a Reset Query and
dumps every PDU: VRPs, Router Keys, End of Data with the serial. Exists
because NIST's own `rpkirtr_client` is linked against a libreadline the images
do not ship and fails in both the router and srx-server images.

**`bgpsec_dissect.py`** — parses `BGPsec_PATH` attributes (RFC 8205) straight
out of a pcap's raw bytes: the Secure_Path AS chain, and every signature
segment's SKI and length. No tshark needed — Wireshark has understood BGPsec
since 3.2, but tshark is not installed everywhere and a missing package should
not cost a student the exercise.

**`build_notebook.py`** — the notebook source. All prose, all code cells, and
all model answers live here; cells tagged `teacher` appear only in the
instructor build.

**`run_notebook.py`** — executes a notebook's code cells in order in one shared
namespace, the way a kernel would, and stops at the first exception. This is
the check behind the exit criterion. (`nbconvert --execute` would be the
obvious tool; it is not installed, and this lab should not require adding
packages to verify itself.)

**`smoke_test.py`** — drives all four parts headless with the same assertions
the notebook makes, in about eleven minutes. The fastest way to tell whether a
change broke an exercise. Run it after touching `gen_configs.py`, `labkit.py`
or anything in `overlay/`.

### `lab/phase4/` — the lab itself

**`bgpsec-p4.clab.yml`** — the topology: eleven nodes, five links, all
staging, all binds. Its header comments carry the addressing table and the
capture points.
**`configs/a|b|c|d/`** — generated router configs.
**`configs/active/`** — what is currently bound into the containers.
**`keys/`** — the key vault (§7).
**`state/rsync_repo/`, `state/rsync_ta/`** — the publication point and trust
anchor, shared between Krill, rsyncd and Routinator. Written by containers
running as root; clear them through a container, not with `sudo`.
**`captures/`** — pcaps written by `labkit.capture()`.
**`clab-bgpsec-p4/`** — containerlab's own runtime directory: inventories, TLS
material, and `graph/` with dot and mermaid renderings of the topology.
**This directory is recreated on every deploy**, so anything in it is
disposable — regenerate the diagrams with
`containerlab graph -t phase4/bgpsec-p4.clab.yml --mermaid` (or `--dot`).

---

## 12. `labkit.py` reference

Import once: `import labkit as lab`.

### Constants

`PREFIX` the prefix the lab is about (`10.64.2.0/24`) · `ORIGIN` `VICTIM`
`OBSERVER` `ATTACKER` node names · `ATTACKER_PEER` / `LEGIT_PEER` the two peer
addresses AS64604 sees · `ROUTERS`, `QUAGGA` node lists · `LINKS` the four
inter-AS capture points in announcement order.

### Reading state

| Call | Returns |
|---|---|
| `routes(node, prefix=PREFIX)` | every path the router holds, as `Route` objects |
| `best(node)` | the path traffic actually follows, or `None` |
| `show(node)` | prints the paths, best first — the main observation call |
| `observer_routes()` | the same for AS64605 (called automatically by `routes`) |
| `sessions(node)` | `{peer address: state}` |
| `status()` | one screen: all sessions, RPKI counts, both best paths |

A **`Route`** carries: `as_path`, `peer`, `origin_state` and `path_state`
(`valid` / `invalid` / `notfound` / `disabled` / `-`), `localpref` with its
`localpref_base` and `localpref_delta` components, `best`, `ignored` (dropped
by policy), `signed` (arrived as a BGPsec path), and `segments` — the per-hop
`(ASN, SKI)` chain the router verified.

`routes()` parses `show ip bgp <prefix>`, the **detail** form, not the table.
The table's columns are ambiguous: AS numbers and the metric/local-pref/weight
columns are all bare integers with no dependable alignment, so a parser cannot
tell where the path starts. The detail form puts the AS path on its own line,
spells validation results out in words, marks ignored routes explicitly, and
carries the full signature chain.

### Waiting

Everything polls; nothing sleeps a fixed interval. Convergence took anywhere
from 20 to 35 seconds during development and was not stable.

| Call | Waits for |
|---|---|
| `wait_converged()` | every BGP session Established |
| `wait_for_best(node, via=, as_path=)` | the router's *chosen* path to match |
| `wait_for_route(node, via=, settled=True)` | a matching path to *exist* and be judged |
| `wait_for_gone(node, via=)` | the router to stop using a path |
| `wait_for(fn, description)` | any condition you like |

**`wait_for_route` versus `wait_for_best` is the subtlest thing in the file.**
Once a defence is on, an attack still *arrives*, it just stops being *used*.
Waiting for it to become best would hang forever; not waiting at all races the
announcement and reports that the attack was never mounted. `settled=True`
additionally waits for the router to have finished judging — a path appears in
the table a moment before the validator has answered for it, and reading it in
that window shows `undefined` and reports the wrong thing intermittently.

### Driving

| Call | Does |
|---|---|
| `deploy()` | brings the lab up in Part A; safe to re-run |
| `set_part("a".."d")` | switches curriculum state and waits |
| `attack("hijack" / "forge" / "stop")` | mounts or withdraws an attack |
| `reset()` | Part A, no attack, no ROA |
| `destroy()` | tears the lab down |
| `vty(node, *cmds, config=False)` | raw VTY access |
| `restart_daemon(node)` | in-place daemon restart |

`deploy()` waits for sessions **and** for the prefix to reach the far end —
sessions being Established is not the same as the lab being ready, and the
notebook's first observation would otherwise show the observer with no route.

### RPKI

| Call | Does |
|---|---|
| `add_roa()` / `remove_roa()` | issue or withdraw the ROA, wait for Routinator |
| `roas()` | list what the CA holds |
| `vrp_count()` / `router_key_count()` | what Routinator is serving |
| `rtr_dump()` | every PDU the validator will hand a router, right now |
| `revoke_router_key(asn)` / `restore_router_key(asn)` | withdraw / re-issue a router certificate |
| `skis()` | `{ASN: SKI}` from the vault |
| `krillc(*args)` | raw CA access |

### Packets

| Call | Does |
|---|---|
| `capture(node, iface, seconds, reset_peer=)` | tcpdump on one link, returns a pcap path |
| `dissect(pcap)` | every `BGPsec_PATH`, as `Signed` objects |
| `signature_growth()` | walks all four links, returns `(label, hops, signatures)` |

Reset the session **next to** the capture point. A reset further upstream may
not produce an UPDATE on this link inside the capture window — a lesson from
Phase 3, where the first attempt at the four-link capture came back empty.

### Assertions

`check(claim, ok, detail="")` prints one line stating what was verified.
`checkpoint(name)` summarises and says whether it is safe to continue.

`check()` **prints rather than raises** on purpose: a failed assertion should
tell the student what is wrong and let them keep reading, not abort the
notebook mid-exercise.

`preflight()` checks architecture, memory, Docker, containerlab, group
membership and images, and names the specific fix for anything missing.

---

## 13. Constraints that shaped the design

Behaviours discovered by measurement that the lab has to work around. These
are the expensive knowledge in this repository.

**Containerlab veths do not survive container recreation.** A `docker restart`,
or a Docker daemon restart after a reboot, leaves every router with only
`eth0`. All containers show `Up`, every address the topology applied is gone,
and nothing reports an error. Recovery is `destroy --cleanup` then `deploy`.

**BGPsec cannot be toggled on a live session** (QuaggaSRx). It takes effect
only at daemon start; a live toggle wedges the session in Idle with
`Missing well-known attribute 3`.

**A signing QuaggaSRx cannot speak plain BGP to one neighbour.** With
`srx bgpsec active` set it signs on *every* session regardless of the
per-neighbour setting — `bgpsec rec` ("send BGP4 only") and omitting the line
entirely both still sign, and both break the session. This is why Part D's gap
sits at the origin rather than mid-chain: signing → plain is the direction that
breaks; plain → signing works.

**An unsigned route on a BGPsec session scores Invalid, not unknown.** So a
"drop invalid" policy in a partly-deployed world disconnects everyone who has
not deployed.

**SRx-server keeps stale client registrations**, keyed by proxy ID, outliving
the router that made them. This produced the worst failure mode in the
project: every session Established, no router holding any routes, and nothing
in any log naming the cause.

**GoBGP marks but does not act.** Origin validation alone changed nothing until
an explicit `rov-drop-invalid` import policy was added. Worth showing students:
the validator's opinion and the router's behaviour are two different things.

**GoBGP's JSON output omits validation state**, so the observer is read from
the text table. Its age column is bare digits and colons, exactly like an AS
number — the age pattern has to be pinned to `HH:MM:SS` or the parser silently
truncates the AS path and succeeds with a wrong answer.

**QuaggaSRx has no `show srx`-style commands** and no `vtysh` in the image.
SRx state is visible only through `show ip bgp` and the SRx console on 17901.

**`srx policy origin ignore undefined` is on by default** — a validator outage
becomes a routing outage unless you turn it off.

---

## 14. Debugging recipes

**Start here, always:**

```python
import labkit as lab
lab.status()
```

**Every session Established but no routes anywhere.** Almost certainly
`srx_server` with a stale client table. Confirm by checking a router's proxy
state; fix with a part switch, which restarts the engine first.

```bash
docker logs clab-bgpsec-p4-as64601 2>&1 | grep -i srxproxy | tail -2
# `isConnected (bgp->srxProxy): 0` confirms it
python3 -c "import labkit as lab; lab.set_part('c')"   # current part
```

**A router has only `eth0`.** Containers were recreated. Redeploy.

```bash
docker exec clab-bgpsec-p4-as64604 ip -br addr
containerlab destroy -t phase4/bgpsec-p4.clab.yml --cleanup
containerlab deploy -t phase4/bgpsec-p4.clab.yml
```

**A session flaps with `Missing well-known attribute 3`.** One end is signing
and the other is not. Check what part is actually bound:

```bash
head -1 phase4/configs/active/quagga_as64604.conf
grep -E "bgpsec|neighbor" phase4/configs/active/quagga_as64603.conf
```

**A ROA is not reaching the routers.** Walk the chain in order and stop at the
first zero:

```python
lab.roas()              # is it in the CA?
lab.vrp_count()         # has the validator picked it up?  (≤30s)
print(lab.rtr_dump())   # will the validator serve it?
lab.show(lab.VICTIM)    # has the router acted on it?
```

**The VTY says "configuration is locked by other VTY".** A previous session
died in config mode. Restart the daemon — the container survives:

```bash
docker exec clab-bgpsec-p4-as64604 pkill -x bgpd
```

**A capture came back empty.** You reset the wrong session. Reset the one
adjacent to the interface you are capturing on.

**Something in the curriculum broke.** Run the smoke test; it names the part
and the assertion:

```bash
python3 tools/smoke_test.py c        # or a b c d
```

**Verify the whole deliverable still works** (about fifteen minutes):

```bash
python3 tools/run_notebook.py bgpsec-lab.ipynb
```

[sidn]: https://github.com/SIDN/bgpsec-testbed
