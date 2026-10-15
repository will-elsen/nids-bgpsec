#!/usr/bin/env python3
"""Generate the four per-part router config sets for the Phase 4 topology.

    gen_configs.py <phase4-dir>

The curriculum walks the same five routers through four states:

    a  unprotected      no origin validation, no BGPsec
    b  ROV              origin validation on, BGPsec still off
    c  BGPsec           both on
    d  partial          both on, except AS64603 speaks plain BGP

Writing those by hand would be twenty files with the same SKIs, neighbours and
policy lines copied through each — one edit away from a lab that teaches the
wrong thing because a stale config is bound. So the topology lives in the
table below and the files are generated. `set_part.sh` copies one set into
configs/active/ and restarts the daemons in place.

SKIs are read from the vault's ski-list.txt rather than hardcoded, so
regenerating keys does not silently leave configs pointing at dead ones.

A session negotiates BGPsec only if *both* ends have it enabled, which is what
makes part d work: turning AS64603 off automatically drops BGPsec from its two
sessions without touching its neighbours' entries.
"""
import os
import sys

# asn -> (router-id, [(peer-ip, peer-asn)], [originated prefixes])
#
# Two deviations from the plan's topology, both forced by measurement on
# 2026-07-31 and both about making the attacks succeed for the right reason.
#
# 1. There are five legitimate ASes, not four: AS64601 sits between the origin
#    and AS64603. The attacker's forged path is always exactly two hops
#    ("64666 64602"), so it only wins where the real path is longer than that.
#    In the plan's four-AS chain the real path reaches AS64604 in two hops as
#    well; the two tie and the tie breaks on router-id, so the attack fails
#    for a reason that teaches nothing about routing security. With AS64601 in
#    the chain the real path is three hops and the forgery wins on merit.
#
# 2. The attacker peers with AS64604, a QuaggaSRx router, which is therefore
#    where the attacks are judged. AS64605 stays the GoBGP-SRx observer.
#    QuaggaSRx is the only one of the two with policy that can act on a BGPsec
#    result — `srx policy bgpsec ignore invalid` — so it has to be the victim;
#    GoBGP-SRx marks a bad path and then uses it anyway.
ROUTERS = {
    64602: ("10.0.0.2", [("10.21.0.1", 64601)], ["10.64.2.0/24"]),
    # .7, not .1: 10.0.0.1 is the mgmt bridge's own gateway address, and
    # containerlab fails the node with "Address already in use".
    64601: ("10.0.0.7", [("10.21.0.2", 64602), ("10.13.0.3", 64603)], []),
    64603: ("10.0.0.3", [("10.13.0.1", 64601), ("10.34.0.4", 64604)], []),
    64604: ("10.0.0.4", [("10.34.0.3", 64603), ("10.45.0.5", 64605),
                         ("10.46.0.6", 64666)], []),
    64666: ("10.0.0.6", [("10.46.0.4", 64604)], []),   # attacker, see below
}
GOBGP_ASN = 64605
# router-id, [(peer-ip, peer-asn)]
GOBGP = ("10.0.0.5", [("10.45.0.4", 64604)])

ATTACKER = 64666

# part -> (origin validation on, set of ASNs running BGPsec)
BGPSEC_ALL = {64601, 64602, 64603, 64604, 64605, 64666}
PARTS = {
    "a": (False, set()),
    "b": (True,  set()),
    "c": (True,  BGPSEC_ALL),
    # The gap is at the origin, not in the middle. A middle gap is what the
    # plan asks for and what the lesson wants, but QuaggaSRx cannot build it:
    # a router with `srx bgpsec active` signs on every session no matter what
    # the per-neighbour setting says (`bgpsec rec`, or the line omitted
    # entirely — both tested 2026-07-31), so the plain-BGP neighbour rejects
    # the UPDATE with "Missing well-known attribute 3" and the session never
    # establishes. The route stops dead instead of arriving unprovable, which
    # is not the same lesson. Signing router -> plain router is the direction
    # that breaks; plain router -> signing router works, so the gap has to sit
    # upstream of everyone who signs.
    "d": (True,  BGPSEC_ALL - {64602}),
}

PART_BLURB = {
    "a": "Part A — the unprotected internet. Nothing is validated; both\n"
         "! attacks succeed. This is the state students start in.",
    "b": "Part B — RPKI and ROV. Origin validation is on and invalid routes\n"
         "! are dropped, which stops the plain hijack. The forged path still\n"
         "! gets through, because the origin it names is the authorised one.",
    "c": "Part C — BGPsec. Every session signs and verifies the path, so the\n"
         "! forged adjacency to AS64602 can no longer be manufactured.",
    "d": "Part D — partial deployment. As part C, except AS64603 speaks plain\n"
         "! BGP. The signature chain breaks in the middle and AS64605 can no\n"
         "! longer prove anything about the hops beyond the gap.",
}


def read_skis(vault):
    skis = {}
    with open(os.path.join(vault, "ski-list.txt")) as fh:
        for line in fh:
            if "-SKI:" in line:
                asn, ski = line.split("-SKI:")
                skis[int(asn)] = ski.strip()
    return skis


def quagga(asn, part, skis):
    rid, neighbours, networks = ROUTERS[asn]
    rov, bgpsec_ases = PARTS[part]
    signs = asn in bgpsec_ases
    out = [
        f"! AS{asn} — generated by lab/tools/gen_configs.py for part {part}.",
        f"! Do not edit: regenerate instead, or the next set_part.sh overwrites it.",
        "!",
        f"! {PART_BLURB[part]}",
        "hostname bgpd",
        "password zebra",
        f"router bgp {asn}",
        f"  bgp router-id {rid}",
        "  srx display",
        f"  srx set-proxy-id {rid}",
        "  srx set-server 10.0.0.15 17900",
        "  srx connect",
        "  no srx extcommunity",
    ]

    # Validation. Stated explicitly in every part, including the negative
    # form — `show running-config` does not reliably reflect these, so the
    # config file is the only honest record of what the router was asked to do.
    # Fail open if the validator is unreachable. QuaggaSRx defaults to
    # `srx policy origin ignore undefined`, which drops any route SRx has not
    # answered for — so a hiccup in srx_server silently turns into "this
    # router has no internet", which looks exactly like a broken lab and is
    # nothing to do with the exercise. Real deployments make the same choice
    # for the same reason: losing your validator should not lose your routes.
    out += ["  no srx policy origin ignore undefined"]

    if rov:
        out += [
            "  srx evaluation origin",
            "  srx set-origin-value undefined",
            "  srx policy origin local-preference valid add 20",
            # Drop, rather than de-prefer: this is the behaviour operators
            # actually deploy, and it is what makes the hijack in Part B
            # disappear rather than merely lose.
            "  srx policy origin ignore invalid",
        ]
    else:
        out += ["  no srx evaluation origin"]

    if signs:
        out += [
            "  srx evaluation bgpsec distributed",
            "  srx set-bgpsec-value undefined",
            "  srx policy bgpsec local-preference valid add 20",
        ]
        if part == "d":
            # Partial deployment forces the choice the real internet faces.
            # An unsigned route arriving on a BGPsec session scores *invalid*,
            # not "unknown" (measured 2026-07-31), so dropping invalids here
            # would disconnect every AS that has not deployed BGPsec — which
            # is nearly all of them. Accepting and de-preferring is what an
            # operator would actually do, and it leaves the route in the table
            # for students to ask what AS64605 can still prove about it.
            out += [
                "  no srx policy bgpsec ignore invalid",
                "  srx policy bgpsec local-preference invalid subtract 20",
            ]
        else:
            out += ["  srx policy bgpsec ignore invalid"]
        out += [
            "  no srx policy bgpsec ignore undefined",
            f"  srx bgpsec ski 0 1 {skis[asn]}",
            "  srx bgpsec active 0",
        ]
    else:
        out += ["  no srx evaluation bgpsec"]

    for prefix in networks:
        out.append(f"  network {prefix}")

    for peer_ip, peer_asn in neighbours:
        out.append(f"  neighbor {peer_ip} remote-as {peer_asn}")
        # Both ends must agree, or the session never comes up.
        if signs and peer_asn in bgpsec_ases:
            out.append(f"  neighbor {peer_ip} bgpsec both")
        elif signs:
            # Peer does not do BGPsec (part d). Omitting the line is not
            # enough: a router with `srx bgpsec active` signs on every session
            # regardless, and the plain-BGP peer answers "Missing well-known
            # attribute 3" and drops the session — the gap never forms, the
            # route simply stops. `rec` is the explicit "send BGP4 only, still
            # accept BGPsec inbound" setting, which is what a real
            # partially-deployed edge looks like.
            out.append(f"  neighbor {peer_ip} bgpsec rec")
        out.append(f"  neighbor {peer_ip} timers connect 5")

    if asn == ATTACKER:
        out += [
            "!",
            "! The attacker announces nothing until an exercise cell tells it to:",
            "!   origin hijack   network 10.64.2.0/24",
            "!   path forgery    neighbor 10.46.0.4 route-map forge-origin out",
            "! The forgery prepends the real owner's ASN, so the route appears to",
            "! come from AS64602 one hop away. Nothing about that is privileged —",
            "! it is a route-map any operator can write.",
            "route-map forge-origin permit 10",
            "  set as-path prepend 64602",
        ]

    out += ["!", "log stdout", ""]
    return "\n".join(out)


def gobgp(part, skis):
    rid, neighbours = GOBGP
    rov, bgpsec_ases = PARTS[part]
    signs = GOBGP_ASN in bgpsec_ases
    out = [
        f"# AS{GOBGP_ASN} — generated by lab/tools/gen_configs.py for part {part}.",
        "# The observer, and the target: it buys transit from AS64604 and also",
        "# peers with AS64666, which is where every attack arrives.",
        "# Unlike the QuaggaSRx routers it does not use srx-server; it validates",
        "# locally via srx-crypto-api against the shared key vault. Its status",
        "# column reads <origin>,<bgpsec> — see phase3/PHASE3.md.",
        "[global.config]",
        f'  as = "{GOBGP_ASN}"',
        f'  router-id = "{rid}"',
        '  key-path = "/var/lib/bgpsec-keys"',
    ]
    if rov:
        # GoBGP-SRx keeps upstream GoBGP's own RTR client, so the observer does
        # origin validation itself rather than through srx-server. Worth being
        # explicit about, because the plan's implementation table says
        # "no RTR integration" for GoBGP-SRx — that is true of *router key*
        # PDUs, which it reads from the local vault, but not of VRPs. Verified
        # 2026-07-31: `gobgp rpki server` is present and functional.
        out += [
            "",
            "[[rpki-servers]]",
            "  [rpki-servers.config]",
            '    address = "10.0.0.14"',
            "    port = 3323",
            "",
            "# Marking a route Invalid changes nothing on its own — GoBGP will",
            "# still select it as best. Dropping invalids is a policy decision,",
            "# and this is it. Without this block the Part B hijack is labelled",
            "# and then used anyway, which is a real deployment failure mode but",
            "# not the one the exercise is about.",
            "[[policy-definitions]]",
            '  name = "rov-drop-invalid"',
            "  [[policy-definitions.statements]]",
            '    name = "drop-invalid"',
            "    [policy-definitions.statements.conditions.bgp-conditions]",
            '      rpki-validation-result = "invalid"',
            "    [policy-definitions.statements.actions]",
            '      route-disposition = "reject-route"',
            "",
            "[global.apply-policy.config]",
            '  import-policy-list = ["rov-drop-invalid"]',
            '  default-import-policy = "accept-route"',
        ]
    for peer_ip, peer_asn in neighbours:
        out += [
            "",
            "[[neighbors]]",
            "  [neighbors.config]",
            f'    neighbor-address = "{peer_ip}"',
            f'    peer-as = "{peer_asn}"',
            f"    bgpsec-enable = {'true' if signs and peer_asn in bgpsec_ases else 'false'}",
            f'    SKI = "{skis[GOBGP_ASN]}"',
        ]
    out.append("")
    return "\n".join(out)


def main():
    phase4 = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
    skis = read_skis(os.path.join(phase4, "keys"))
    missing = (set(ROUTERS) | {GOBGP_ASN}) - set(skis)
    if missing:
        sys.exit(f"no key in the vault for: {sorted(missing)}")

    for part in PARTS:
        outdir = os.path.join(phase4, "configs", part)
        os.makedirs(outdir, exist_ok=True)
        for asn in ROUTERS:
            with open(os.path.join(outdir, f"quagga_as{asn}.conf"), "w",
                      encoding="utf-8", newline="\n") as fh:
                fh.write(quagga(asn, part, skis))
        with open(os.path.join(outdir, f"gobgpd-as{GOBGP_ASN}.conf"), "w",
                  encoding="utf-8", newline="\n") as fh:
            fh.write(gobgp(part, skis))
        print(f"part {part}: {len(ROUTERS) + 1} configs -> configs/{part}/")


if __name__ == "__main__":
    main()
