"""labkit — the plumbing behind the BGPsec lab notebook.

Everything a notebook cell needs to drive the lab, read its state, and assert
on it. Import it once at the top of the notebook:

    import labkit as lab

Design rules, all of them learned the hard way in Phases 1-4:

* **Nothing here needs sudo.** Containerlab is installed setuid, students are
  in the `docker` group, and packet capture runs as `docker exec <node>
  tcpdump` rather than `ip netns exec`. A password prompt inside a notebook
  cell hangs it with no visible prompt, so a helper that needs root is a
  helper that breaks the lab.

* **Poll, never sleep.** Config changes take 20-35s to converge and the time
  varies. Every wait here polls for the condition and returns as soon as it
  holds, so a student who runs a cell too early gets the right answer slowly
  rather than the wrong answer quickly.

* **Assertions say what they checked.** `check()` prints one line naming the
  thing it verified. A student answering a synthesis question from a lab that
  silently failed to converge learns the wrong lesson.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import struct
import subprocess
import time
from dataclasses import dataclass, field

# --- where things are -------------------------------------------------------

LAB_NAME = "bgpsec-p4"
NODE_PREFIX = f"clab-{LAB_NAME}"
HERE = os.path.dirname(os.path.abspath(__file__))
PHASE4 = os.path.join(HERE, "phase4")
TOPOLOGY = os.path.join(PHASE4, f"{LAB_NAME}.clab.yml")
TOOLS = os.path.join(HERE, "tools")
VAULT = os.path.join(PHASE4, "keys")     #: built from the tracked keys by tools/build_vault.sh
IMAGE_TARBALL = os.path.join(HERE, "dist", "bgpsec-lab-images.tar.gz")

#: The prefix the whole lab is about: AS64602 owns it, AS64666 wants it.
PREFIX = "10.64.2.0/24"

ORIGIN = "as64602"       #: owns PREFIX
VICTIM = "as64604"       #: QuaggaSRx, peers with the attacker, judges every attack
OBSERVER = "as64605"     #: GoBGP-SRx, end of the chain
ATTACKER = "as64666"

QUAGGA = ["as64601", "as64602", "as64603", "as64604", "as64666"]
ROUTERS = QUAGGA + [OBSERVER]

#: Peer address of the attacker, as seen by the victim — "via the attacker".
ATTACKER_PEER = "10.46.0.6"
#: Peer address of AS64603, as seen by the victim — "via the real chain".
LEGIT_PEER = "10.34.0.3"

KRILL_TOKEN = "a_random_admin_token"
KRILL_URL = "http://10.0.0.10:3000/"
ROUTINATOR_METRICS = "http://10.0.0.14:9556/metrics"
RTR_HOST, RTR_PORT = "10.0.0.14", 3323

#: Inter-AS links, in the order the announcement travels. Each entry is
#: (node to capture on, interface, human label). Capturing on the interface
#: next to the session you reset is what makes a capture reliable — a reset
#: further upstream may not reach this link inside the capture window.
LINKS = [
    ("as64602", "eth1", "AS64602 -> AS64601"),
    ("as64601", "eth2", "AS64601 -> AS64603"),
    ("as64603", "eth2", "AS64603 -> AS64604"),
    ("as64604", "eth2", "AS64604 -> AS64605"),
]


class LabError(RuntimeError):
    """Something the student needs to fix before continuing."""


# --- talking to containers --------------------------------------------------

def _run(args: list[str], timeout: int = 120, check_rc: bool = True) -> str:
    proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if check_rc and proc.returncode != 0:
        raise LabError(f"{' '.join(args[:3])} failed: {proc.stderr.strip() or proc.stdout.strip()}")
    return proc.stdout


def node(name: str) -> str:
    """Container name for a node — `node('as64604')` -> the full clab name."""
    return name if name.startswith(NODE_PREFIX) else f"{NODE_PREFIX}-{name}"


def dexec(name: str, *args: str, timeout: int = 120, check_rc: bool = True) -> str:
    return _run(["docker", "exec", node(name), *args], timeout=timeout, check_rc=check_rc)


def vty(name: str, *commands: str, config: bool = False) -> str:
    """Run commands on a QuaggaSRx VTY and return the raw output.

    The image ships neither `vtysh` nor a unix socket, so this telnets to
    bgpd's VTY on 2605 the way a human would. `config=True` wraps the commands
    in `configure terminal` / `router bgp <asn>` and closes with `end` —
    leaving a session in config mode locks the VTY for everyone else, and the
    only way out is restarting the daemon.
    """
    asn = name.split("as")[-1]
    script = ["echo zebra", "sleep 1", "echo enable", "sleep 1"]
    if config:
        script += ["echo 'configure terminal'", "sleep 1", f"echo 'router bgp {asn}'", "sleep 1"]
    for cmd in commands:
        script += [f"echo '{cmd}'", "sleep 2"]
    if config:
        script += ["echo end", "sleep 1"]
    script.append("sleep 1")
    inner = "; ".join(script)
    out = dexec(name, "bash", "-c", f"({inner}) | telnet localhost 2605")
    return out


def restart_daemon(name: str) -> None:
    """Restart a router's daemon in place, keeping the container and its links.

    `docker restart` would recreate the container, and containerlab's veth
    pairs do not survive that — the node comes back with only eth0 and the lab
    looks deployed while being quietly broken. The images run a supervisor as
    PID 1 precisely so this is possible.
    """
    daemon = "gobgpd" if name == OBSERVER else "bgpd"
    dexec(name, "pkill", "-x", daemon, check_rc=False)


# --- reading routing state --------------------------------------------------

@dataclass
class Route:
    """One path for one prefix, as a QuaggaSRx router sees it."""
    as_path: list[int]
    peer: str = ""
    origin_state: str = "-"      #: valid / invalid / notfound / undefined / -
    path_state: str = "-"        #: BGPsec: valid / invalid / notfound / undefined / -
    localpref: int = 100
    localpref_base: int = 100
    localpref_delta: int = 0
    best: bool = False
    ignored: bool = False        #: dropped by an `srx policy ... ignore` rule
    signed: bool = False         #: a BGPsec_PATH attribute came with it
    update_id: str = ""          #: QuaggaSRx's handle for this path
    #: One (ASN, SKI) per signature segment, newest signer first. Populated
    #: only for signed paths — this is the router telling you which key it
    #: checked each hop against, and the SKIs match the Router Key PDUs the
    #: validator serves over RTR.
    segments: list[tuple[int, str]] = field(default_factory=list)

    @property
    def via_attacker(self) -> bool:
        return self.peer == ATTACKER_PEER

    @property
    def origin_as(self) -> int | None:
        return self.as_path[-1] if self.as_path else None

    def __str__(self) -> str:
        marks = ("best" if self.best else "") + (" ignored" if self.ignored else "")
        return (f"{' '.join(map(str, self.as_path)) or 'local':<22} via {self.peer:<11} "
                f"origin={self.origin_state:<9} path={self.path_state:<9} "
                f"lp={self.localpref:<4} {marks}")


_PATH_LINE = re.compile(r"^  (\d+(?: \d+)*|Local)\s*$")
_LOCALPREF = re.compile(r"localpref (\d+)\+(-?\d+)=(\d+)")


def routes(name: str, prefix: str = PREFIX) -> list[Route]:
    """Every path a QuaggaSRx router holds for `prefix`, validation included.

    Parses `show ip bgp <prefix>`, the detail form, rather than the table.
    The table's columns are ambiguous — AS numbers and the weight/metric
    columns are both bare integers with no reliable alignment — while the
    detail form puts the AS path on its own line and spells the validation
    results out in words.
    """
    if name == OBSERVER:
        return observer_routes(prefix)
    out = vty(name, f"show ip bgp {prefix}")
    found: list[Route] = []
    current: Route | None = None
    for line in out.splitlines():
        m = _PATH_LINE.match(line.rstrip())
        if m:
            hops = [] if m.group(1) == "Local" else [int(a) for a in m.group(1).split()]
            current = Route(as_path=hops)
            found.append(current)
            continue
        if current is None:
            continue
        stripped = line.strip()
        if stripped.startswith("prefix-origin:"):
            current.origin_state = _state(stripped)
        elif stripped.startswith("path:"):
            current.path_state = _state(stripped)
        elif stripped.startswith("Update ID:"):
            current.update_id = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("PathType:"):
            # QuaggaSRx names the attribute the path arrived in: AS-PATH for a
            # plain UPDATE, BGPSEC-Path when a BGPsec_PATH was present. This is
            # the only place the router says whether the route was signed at
            # all, as distinct from whether the signature verified.
            current.signed = "BGPSEC" in stripped.upper()
        elif stripped.startswith("This update will be ignored"):
            # The per-path form of the table view's `I` flag: policy told the
            # router to disregard this route, so it can never become best no
            # matter how attractive its attributes are.
            current.ignored = True
        elif stripped.startswith("path segment"):
            m = re.search(r"as=(\d+)", stripped)
            if m:
                current.segments.append((int(m.group(1)), ""))
        elif stripped.startswith("signature segment") and current.segments:
            m = re.search(r"ski=([0-9A-Fa-f]+)", stripped)
            if m:
                asn, _ = current.segments[-1]
                current.segments[-1] = (asn, m.group(1).upper())
        elif " from " in stripped and not stripped.startswith("Last"):
            current.peer = stripped.split(" from ", 1)[0].strip()
        elif stripped.startswith("Origin "):
            lp = _LOCALPREF.search(stripped)
            if lp:
                current.localpref_base = int(lp.group(1))
                current.localpref_delta = int(lp.group(2))
                current.localpref = int(lp.group(3))
            current.best = ", best" in stripped
    return found


def _state(line: str) -> str:
    """Normalise one validation result.

    QuaggaSRx says "processing disabled!" for an axis it was not asked to
    evaluate. That is worth surfacing — it is the difference between "checked
    and found fine" and "never checked" — but not in those words.
    """
    value = line.split(":", 1)[1].strip()
    return "disabled" if value.startswith("processing disabled") else value


# The age column is bare digits and colons, and so is the AS path, so the age
# has to be pinned to its exact HH:MM:SS shape or it swallows the second AS in
# the path and the parse silently succeeds with a wrong answer.
_OBS_LINE = re.compile(
    r"^(?P<origin>[VIN]?),(?P<bgpsec>[VIN]?)\s*(?P<flags>[*>\s]{0,3})\s*"
    r"(?P<net>\d+\.\d+\.\d+\.\d+/\d+)\s+(?P<nh>\S+)\s+(?P<path>(?:\d+\s+)*)"
    r"(?P<age>(?:\d+d )?\d{2}:\d{2}:\d{2})\s+(?P<attrs>.*)$")

_GOBGP_STATE = {"V": "valid", "I": "invalid", "N": "notfound", "": "notfound"}


def observer_routes(prefix: str = PREFIX) -> list[Route]:
    """What the GoBGP-SRx observer holds, in the same shape as `routes()`.

    GoBGP's JSON output omits validation state, so this reads the text table,
    whose leading `<origin>,<bgpsec>` column carries exactly what the exercise
    needs. `signed` is inferred from the `{bgpsecs}` attribute marker.
    """
    out = dexec(OBSERVER, "gobgp", "global", "rib")
    found = []
    for line in out.splitlines():
        m = _OBS_LINE.match(line.rstrip())
        if not m or m.group("net") != prefix:
            continue
        hops = [int(a) for a in m.group("path").split()]
        r = Route(
            as_path=hops,
            peer=m.group("nh"),
            origin_state=_GOBGP_STATE.get(m.group("origin"), "notfound"),
            path_state=_GOBGP_STATE.get(m.group("bgpsec"), "notfound"),
            best=">" in m.group("flags"),
            signed="{bgpsecs}" in m.group("attrs"),
        )
        found.append(r)
    return found


def best(name: str, prefix: str = PREFIX) -> Route | None:
    """The path a router is actually using — the one traffic follows."""
    for r in routes(name, prefix):
        if r.best:
            return r
    return None


def show(name: str, prefix: str = PREFIX) -> None:
    """Print a router's paths for `prefix`, one line each, best first."""
    rs = routes(name, prefix)
    if not rs:
        print(f"{name}: no route to {prefix}")
        return
    print(f"{name}: {len(rs)} path(s) to {prefix}")
    for r in sorted(rs, key=lambda r: not r.best):
        print(f"  {'*>' if r.best else '  '} {r}")


def sessions(name: str) -> dict[str, str]:
    """Peer address -> BGP state, for one router."""
    if name == OBSERVER:
        out = dexec(OBSERVER, "gobgp", "neighbor")
        found = {}
        for line in out.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 4 and re.match(r"\d+\.\d+\.\d+\.\d+", parts[0]):
                found[parts[0]] = "Established" if parts[3].startswith("Estab") else parts[3]
        return found
    out = vty(name, "show ip bgp summary")
    found = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 10 and re.match(r"^\d+\.\d+\.\d+\.\d+$", parts[0]):
            state = parts[9]
            # A numeric last column is a prefix count, which only appears once
            # the session is up; anything else is the state name.
            found[parts[0]] = "Established" if state.isdigit() else state
    return found


# --- waiting ----------------------------------------------------------------

def wait_for(condition, what: str, timeout: int = 120, interval: float = 4.0):
    """Poll `condition` until it returns something truthy. Return that value.

    Every state change in this lab is asynchronous: a config swap restarts
    daemons, sessions re-establish, and RPKI data takes a further RTR round
    trip. Timings measured during development ranged from 20s to 35s and are
    not stable, so cells poll rather than sleep.
    """
    deadline = time.time() + timeout
    while True:
        try:
            value = condition()
        except LabError:
            value = None
        if value:
            return value
        if time.time() >= deadline:
            raise LabError(
                f"timed out after {timeout}s waiting for {what}.\n"
                f"    Check `lab.status()` — if sessions are down, the usual cause is a\n"
                f"    config change that has not converged yet, or a daemon that failed\n"
                f"    to start (see `docker logs {NODE_PREFIX}-as64604`)."
            )
        time.sleep(interval)


def wait_converged(timeout: int = 150) -> None:
    """Wait until every BGP session in the lab is Established."""
    def all_up():
        down = []
        for r in ROUTERS:
            for peer, state in sessions(r).items():
                if state != "Established":
                    down.append(f"{r}->{peer} ({state})")
        return not down
    wait_for(all_up, "all BGP sessions to establish", timeout=timeout)


def wait_for_best(name: str, via: str | None = None, as_path: list[int] | None = None,
                  prefix: str = PREFIX, timeout: int = 120) -> Route:
    """Wait until `name`'s best path matches, and return it."""
    def matches():
        r = best(name, prefix)
        if r is None:
            return None
        if via is not None and r.peer != via:
            return None
        if as_path is not None and r.as_path != as_path:
            return None
        return r
    want = f"{name} to prefer {prefix}" + (f" via {via}" if via else "")
    return wait_for(matches, want, timeout=timeout)


def wait_for_route(name: str, via: str | None = None, as_path: list[int] | None = None,
                   prefix: str = PREFIX, settled: bool = True,
                   timeout: int = 120) -> Route:
    """Wait until a matching path *exists*, best or not, and return it.

    Distinct from `wait_for_best`, and the distinction matters: once a defence
    is switched on, an attack still arrives, it just stops being used. Waiting
    for it to become best would wait forever; not waiting at all races the
    announcement and reports that the attack was never mounted.

    `settled` additionally waits for the router to have finished judging the
    route. A path shows up in the table before SRx has answered for it, and a
    check that reads it in that window sees `undefined` and reports the wrong
    thing intermittently. Waiting for a verdict — without caring which verdict
    — keeps the assertion honest.
    """
    def present():
        for r in routes(name, prefix):
            if via is not None and r.peer != via:
                continue
            if as_path is not None and r.as_path != as_path:
                continue
            if settled and "undefined" in (r.origin_state, r.path_state):
                continue
            return r
        return None
    want = f"a path at {name}" + (f" via {via}" if via else "")
    return wait_for(present, want, timeout=timeout)


def wait_for_gone(name: str, via: str, prefix: str = PREFIX, timeout: int = 120) -> None:
    """Wait until `name` is no longer *using* the path learned from `via`."""
    def gone():
        r = best(name, prefix)
        return r is not None and r.peer != via
    wait_for(gone, f"{name} to stop using the path via {via}", timeout=timeout)


# --- driving the lab --------------------------------------------------------

def set_part(part: str) -> None:
    """Move the lab to curriculum state a, b, c or d, and wait for it.

    Swaps the bound configs and restarts each daemon in place. RPKI state —
    ROAs in Krill, the router certificates — is deliberately untouched, so a
    ROA issued in Part B is still there in Part C.

    A restart also drops any attack the attacker was announcing, because those
    are runtime commands rather than config. That is why each part re-runs the
    attacks explicitly.
    """
    if part not in "abcd" or len(part) != 1:
        raise LabError(f"part must be a, b, c or d (got {part!r})")
    _run(["bash", os.path.join(TOOLS, "set_part.sh"), PHASE4, part])
    print(f"part {part} active — waiting for sessions to re-establish")
    wait_converged()
    print("converged")


def attack(kind: str) -> None:
    """Have AS64666 mount an attack, or stop.

    `hijack` — announce AS64602's prefix as its own. The path is one AS long,
      so it beats the real three-AS path on length.
    `forge`  — announce the same prefix with AS64602 prepended, so the route
      appears to come from its real owner via a fabricated adjacency. Two AS
      hops: still shorter than the real path.
    `stop`   — withdraw everything.
    """
    if kind == "hijack":
        vty(ATTACKER, "no neighbor 10.46.0.4 route-map forge-origin out",
            "network " + PREFIX, config=True)
    elif kind == "forge":
        vty(ATTACKER, "network " + PREFIX,
            "neighbor 10.46.0.4 route-map forge-origin out", config=True)
    elif kind == "stop":
        vty(ATTACKER, "no network " + PREFIX,
            "no neighbor 10.46.0.4 route-map forge-origin out", config=True)
    else:
        raise LabError(f"unknown attack {kind!r} — use hijack, forge or stop")
    # The route-map only takes effect on routes sent after it is attached.
    vty(ATTACKER, "clear ip bgp 10.46.0.4")


# --- the RPKI side ----------------------------------------------------------

def krillc(*args: str) -> str:
    return dexec("krill", "krillc", *args, "-t", KRILL_TOKEN, "-c", "testbed", "-s", KRILL_URL)


def add_roa(prefix: str = PREFIX, asn: int = 64602) -> None:
    """Authorise `asn` to originate `prefix`, then wait for it to reach the routers."""
    krillc("roas", "update", "--add", f"{prefix} => {asn}")
    wait_for(lambda: vrp_count() >= 1, "the ROA to reach Routinator", timeout=120)
    print(f"ROA issued: {prefix} => AS{asn}, and Routinator is serving it")


def remove_roa(prefix: str = PREFIX, asn: int = 64602) -> None:
    krillc("roas", "update", "--remove", f"{prefix} => {asn}")
    wait_for(lambda: vrp_count() == 0, "the ROA withdrawal to reach Routinator", timeout=120)
    print(f"ROA withdrawn: {prefix} => AS{asn}")


def roas() -> str:
    return krillc("roas", "list")


def revoke_router_key(asn: int = 64602) -> None:
    """Withdraw an AS's BGPsec router certificate from the CA.

    The router keeps its private key and carries on signing exactly as before.
    What changes is that the RPKI no longer vouches for the matching public
    key, so nobody can verify those signatures any more — the failure happens
    entirely outside the routers.
    """
    krillc("bgpsec", "remove", "--asn", f"AS{asn}", "--key", skis()[asn])
    before = router_key_count()
    wait_for(lambda: router_key_count() < before or router_key_count() == 0,
             f"AS{asn}'s router key to disappear from the validator", timeout=150)
    print(f"AS{asn}'s router certificate revoked; Routinator now serves "
          f"{router_key_count()} router key(s)")


def restore_router_key(asn: int = 64602) -> None:
    """Re-issue a revoked router certificate from the CSR still in the vault."""
    ski = skis()[asn]
    # The vault lays keys out the way NIST-BGP-SRx expects: the first two hex
    # characters of the SKI, then the next four, then the rest.
    csr = f"/var/lib/bgpsec-keys/{ski[0:2]}/{ski[2:6]}/{ski[6:]}.csr"
    before = router_key_count()
    krillc("bgpsec", "add", "--asn", f"AS{asn}", "--csr", csr)
    wait_for(lambda: router_key_count() > before,
             f"AS{asn}'s router key to reappear at the validator", timeout=150)
    print(f"AS{asn}'s router certificate re-issued; Routinator now serves "
          f"{router_key_count()} router key(s)")


def vrp_count() -> int:
    """How many validated ROA payloads Routinator is serving from the testbed TA."""
    out = dexec("routinator", "wget", "-qO-", ROUTINATOR_METRICS, check_rc=False)
    m = re.search(r'^routinator_ta_valid_vrps_total\{[^}]*\}\s+(\d+)', out, re.M)
    return int(m.group(1)) if m else 0


def router_key_count() -> int:
    """How many BGPsec router keys Routinator is serving."""
    out = dexec("routinator", "wget", "-qO-", ROUTINATOR_METRICS, check_rc=False)
    m = re.search(r'^routinator_ta_valid_payload_total\{[^}]*type="router_keys"\}\s+(\d+)', out, re.M)
    return int(m.group(1)) if m else 0


def rtr_dump() -> str:
    """Everything Routinator will hand a router over RTR, right now.

    A minimal RFC 8210 client rather than a container tool: NIST's own
    `rpkirtr_client` is linked against a libreadline the images do not ship,
    so it fails in both the router and srx-server images.
    """
    out = _run(["python3", os.path.join(TOOLS, "rtr_query.py"), RTR_HOST, str(RTR_PORT)])
    return out


# --- packets ----------------------------------------------------------------

@dataclass
class Signed:
    """One BGPsec_PATH attribute seen on the wire."""
    secure_path: list[int]
    skis: list[str]
    sig_lengths: list[int] = field(default_factory=list)

    @property
    def hops(self) -> int:
        return len(self.secure_path)

    @property
    def signatures(self) -> int:
        return len(self.skis)


def capture(name: str, iface: str, seconds: int = 30, reset_peer: str | None = None) -> str:
    """Capture BGP on one link and return the path to the pcap.

    Runs tcpdump inside the container — no sudo, no `ip netns exec`. If
    `reset_peer` is given, the session to that peer is cleared once the capture
    is running, which forces a full re-announcement so there is something to
    see. Reset the session *next to* the capture point: a reset further
    upstream may not produce an UPDATE on this link inside the window.
    """
    remote = f"/tmp/{name}-{iface}.pcap"
    local_dir = os.path.join(PHASE4, "captures")
    os.makedirs(local_dir, exist_ok=True)
    local = os.path.join(local_dir, f"{name}-{iface}.pcap")

    _run(["docker", "exec", "-d", node(name), "tcpdump", "-i", iface, "-s0",
          "-w", remote, "tcp", "port", "179"])
    time.sleep(3)
    if reset_peer:
        vty(name, f"clear ip bgp {reset_peer}")
    time.sleep(seconds)
    dexec(name, "pkill", "tcpdump", check_rc=False)
    time.sleep(1)
    _run(["docker", "cp", f"{node(name)}:{remote}", local])
    return local


def dissect(pcap: str) -> list[Signed]:
    """Pull every BGPsec_PATH out of a capture.

    Uses the lab's own dissector rather than tshark. Wireshark has understood
    BGPsec since 3.2.0, but tshark is not installed on every host that can run
    this lab, and a missing package should not cost a student the exercise.
    """
    out = _run(["python3", os.path.join(TOOLS, "bgpsec_dissect.py"), pcap])
    found, current = [], None
    for line in out.splitlines():
        s = line.strip()
        if s.startswith("Secure_Path"):
            asns = [int(a) for a in re.findall(r"AS(\d+)", s)]
            current = Signed(secure_path=asns, skis=[])
            found.append(current)
        elif s.startswith("algo") and current is not None:
            m = re.search(r"SKI ([0-9A-F]+)\s+sig (\d+)B", s)
            if m:
                current.skis.append(m.group(1))
                current.sig_lengths.append(int(m.group(2)))
    return found


def signature_growth(seconds: int = 30) -> list[tuple[str, int, int]]:
    """Walk the chain and count signatures on each link, origin outwards.

    Returns (label, hops, signatures) per link. This is the demonstration the
    whole point-to-point topology exists for: on a shared bridge the signature
    block is unobservable per-hop.
    """
    results = []
    for name, iface, label in LINKS:
        peer = {"as64602": "10.21.0.1", "as64601": "10.13.0.3",
                "as64603": "10.34.0.4", "as64604": "10.45.0.5"}[name]
        pcap = capture(name, iface, seconds=seconds, reset_peer=peer)
        signed = dissect(pcap)
        if signed:
            results.append((label, signed[0].hops, signed[0].signatures))
        else:
            results.append((label, 0, 0))
    return results


def skis() -> dict[int, str]:
    """ASN -> SKI, from the lab's key vault."""
    found = {}
    with open(os.path.join(PHASE4, "keys", "ski-list.txt")) as fh:
        for line in fh:
            if "-SKI:" in line:
                asn, ski = line.split("-SKI:")
                found[int(asn)] = ski.strip()
    return found


# --- assertions -------------------------------------------------------------

_checks = {"passed": 0, "failed": 0}


def check(claim: str, ok: bool, detail: str = "") -> bool:
    """State one thing that was verified, and whether it held.

    Print, don't raise: a failed check should tell the student what is wrong
    and let them keep reading, not abort the notebook mid-exercise.
    """
    mark = "PASS" if ok else "FAIL"
    _checks["passed" if ok else "failed"] += 1
    print(f"[{mark}] {claim}" + (f"\n       {detail}" if detail else ""))
    return ok


def checkpoint(name: str) -> None:
    """Summarise the checks run so far and reset the counter."""
    p, f = _checks["passed"], _checks["failed"]
    _checks["passed"] = _checks["failed"] = 0
    if f:
        print(f"\n{name}: {p} passed, {f} FAILED — fix this before moving on, the "
              f"next exercise builds on it.")
    else:
        print(f"\n{name}: all {p} checks passed.")


# --- setup, status, teardown ------------------------------------------------

def preflight() -> bool:
    """Check the host can run the lab, and say exactly what to fix if not."""
    problems: list[str] = []

    def ok(label, value, fix=None):
        print(f"  {'ok ' if value else 'NO '} {label}")
        if not value and fix:
            problems.append(fix)

    print("Host:")
    arch = os.uname().machine
    ok(f"architecture {arch}", arch == "x86_64",
       "The images are built amd64-only. An arm64 host needs them rebuilt from source.")

    mem_gb = 0
    try:
        with open("/proc/meminfo") as fh:
            mem_gb = int(re.search(r"MemTotal:\s+(\d+)", fh.read()).group(1)) / 1024 / 1024
    except Exception:
        pass
    ok(f"memory {mem_gb:.1f} GiB", mem_gb >= 3.5,
       "The lab runs eleven containers; give the VM at least 4 GiB.")

    print("Tools:")
    ok("docker", shutil.which("docker") is not None,
       "Install Docker, then log out and back in.")
    ok("containerlab", shutil.which("containerlab") is not None,
       "Install containerlab (see quick-setup.sh).")
    ok("openssl", shutil.which("openssl") is not None,
       "Install openssl — the key vault (phase4/keys) is built with it.")

    # The single most likely place to get stuck at minute one: group membership
    # is granted but not yet in effect, because it only applies at login.
    docker_ok = subprocess.run(["docker", "info"], capture_output=True).returncode == 0
    ok("docker usable without sudo", docker_ok,
       "You are probably in the `docker` group but have not logged in again since. "
       "Group membership only takes effect at login: close this session, "
       "start a new one, and rerun. `id -nG` should list `docker`.")

    print("Images:")
    have = _run(["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"], check_rc=False)
    for image in ["bgpsec/quaggasrx:local", "bgpsec/gobgpsrx:local",
                  "bgpsec/srx-server:local", "bgpsec/tal-share:local"]:
        ok(image, image in have,
           f"Missing {image}. Load the bundle: docker load < {IMAGE_TARBALL}")

    if problems:
        print("\nFix these before deploying:\n")
        for p in problems:
            print(f"  * {p}\n")
        return False
    print("\nPreflight passed — you can deploy.")
    return True


def build_vault(force: bool = False) -> None:
    """Build phase4/keys/ from the tracked private keys; a no-op if it exists.

    The vault is not committed — a deploy rewrites its certificates and chowns
    its private keys to root — so a fresh clone has none until this runs.
    tools/build_vault.sh derives it, deterministically, from the vendored
    testbed keys plus the lab's own two in router_keys/, so the SKIs baked
    into the generated configs hold on every machine.
    """
    args = ["bash", os.path.join(TOOLS, "build_vault.sh"), PHASE4]
    if force:
        args.append("--force")
    out = _run(args, timeout=120)
    print(out.strip().splitlines()[0] if out.strip() else "key vault ready")


def deploy() -> None:
    """Bring the lab up in Part A (unprotected) and wait for it to converge.

    Safe to re-run: `--reconfigure` tears down anything already running and
    starts clean, so a student who re-executes the notebook from the top gets
    a fresh lab rather than an error.
    """
    # The topology bind-mounts the vault into every router, so it has to exist
    # before containerlab even parses the file.
    build_vault()

    # Start from Part A's configs — they are what gets bound at container
    # creation, so this has to happen before the deploy, not after.
    shutil.rmtree(os.path.join(PHASE4, "configs", "active"), ignore_errors=True)
    os.makedirs(os.path.join(PHASE4, "configs", "active"), exist_ok=True)
    for name in os.listdir(os.path.join(PHASE4, "configs", "a")):
        shutil.copy(os.path.join(PHASE4, "configs", "a", name),
                    os.path.join(PHASE4, "configs", "active", name))

    # The RPKI publication point and trust anchor are rebuilt from scratch on
    # every deploy. They are written by containers running as root, so they are
    # cleared by a container too rather than by asking the student for a
    # password.
    state = os.path.join(PHASE4, "state")
    _run(["docker", "run", "--rm", "-v", f"{state}:/state", "alpine",
          "sh", "-c", "rm -rf /state/rsync_repo/* /state/rsync_ta/*"], check_rc=False)

    print("deploying — the first run builds an RPKI trust chain, so give it 2-3 minutes")
    _run(["containerlab", "deploy", "-t", TOPOLOGY, "--reconfigure"], timeout=1200)
    wait_converged(timeout=300)
    # Sessions being Established is not the same as the lab being ready: the
    # announcement still has to walk the chain. Without this the notebook's
    # very first observation can show the far end with no route at all, which
    # is a confusing way to open a lab about routing.
    wait_for_best(OBSERVER, as_path=[64604, 64603, 64601, 64602], timeout=180)
    print(f"lab up: {len(ROUTERS)} routers, all sessions Established, "
          f"and {PREFIX} has reached the far end")


def status() -> None:
    """One screen: who is up, what they believe, what the RPKI plane is serving."""
    print(f"{'router':<10} sessions")
    for r in ROUTERS:
        try:
            s = sessions(r)
        except LabError as exc:
            print(f"{r:<10} unreachable ({exc})")
            continue
        summary = ", ".join(f"{p}={st}" for p, st in sorted(s.items()))
        print(f"{r:<10} {summary}")
    print(f"\nRPKI: {vrp_count()} VRP(s), {router_key_count()} router key(s) served over RTR")
    print(f"\nBest path to {PREFIX}:")
    for r in (VICTIM, OBSERVER):
        b = best(r)
        print(f"  {r:<10} {b if b else 'no route'}")


def reset() -> None:
    """Return the lab to its starting state: Part A, no attack, no ROA."""
    try:
        attack("stop")
    except LabError:
        pass
    try:
        if vrp_count():
            remove_roa()
    except LabError:
        pass
    set_part("a")
    print("lab reset to Part A: no validation, no attack, no ROA")


def destroy() -> None:
    """Tear the lab down and free the veths."""
    _run(["containerlab", "destroy", "-t", TOPOLOGY, "--cleanup"], timeout=300)
    print("lab destroyed")
