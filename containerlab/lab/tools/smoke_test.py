"""End-to-end check that labkit can drive the whole curriculum.

Runs the same calls the notebook makes, in the same order, and asserts the
same things. If this passes, every exercise cell in the notebook works; if it
fails, the notebook would have failed in front of a student instead.

    python3 tools/smoke_test.py            # the full A -> B -> C -> D arc
    python3 tools/smoke_test.py a b        # just those parts

Takes about ten minutes for the full run: each part switch restarts five
daemons and waits for four BGP sessions to re-establish.
"""
import sys
import time

sys.path.insert(0, __file__.rsplit("/", 2)[0])
import labkit as lab           # noqa: E402

FORGED = [64666, 64602]
REAL = [64603, 64601, 64602]


def part_a():
    lab.set_part("a")
    if lab.vrp_count():
        lab.remove_roa()

    r = lab.wait_for_best(lab.VICTIM, as_path=REAL)
    lab.check("A1 baseline: AS64604 reaches the prefix through the real chain",
              r.as_path == REAL, str(r))
    lab.check("A1 nothing is validated: no origin or path result",
              r.origin_state in "-" and r.path_state in "-", str(r))

    lab.attack("hijack")
    r = lab.wait_for_best(lab.VICTIM, via=lab.ATTACKER_PEER)
    lab.check("A2 origin hijack: AS64604 now sends traffic to the attacker",
              r.via_attacker and r.as_path == [64666], str(r))

    lab.attack("forge")
    r = lab.wait_for_best(lab.VICTIM, as_path=FORGED)
    lab.check("A3 path forgery: the prefix appears to come from its real owner",
              r.as_path == FORGED and r.via_attacker, str(r))
    obs = lab.wait_for_best(lab.OBSERVER, as_path=[64604] + FORGED)
    lab.check("A3 the forgery reaches the far end of the internet",
              obs.as_path == [64604] + FORGED, str(obs))
    lab.checkpoint("Part A")


def part_b():
    lab.set_part("b")
    lab.attack("stop")
    lab.add_roa()

    r = lab.wait_for_best(lab.VICTIM, as_path=REAL)
    lab.check("B6 the real route is now origin-Valid and preferred",
              r.origin_state == "valid" and r.localpref > 100, str(r))

    lab.attack("hijack")
    # Wait for the attack to *arrive* before asserting it was rejected — the
    # real route is already best, so waiting on best returns instantly and
    # races the announcement.
    hijack = lab.wait_for_route(lab.VICTIM, via=lab.ATTACKER_PEER, timeout=150)
    lab.check("B7 the hijack is rated Invalid and not used",
              hijack.origin_state == "invalid" and not hijack.best, str(hijack))
    r = lab.best(lab.VICTIM)
    lab.check("B7 the real route is the one traffic follows", r.as_path == REAL, str(r))

    lab.attack("forge")
    r = lab.wait_for_best(lab.VICTIM, as_path=FORGED, timeout=150)
    lab.check("B8 ROV rates the forged path VALID — the attack survives",
              r.origin_state == "valid" and r.best, str(r))
    lab.checkpoint("Part B")


def part_c():
    lab.set_part("c")
    lab.attack("stop")

    r = lab.wait_for_best(lab.VICTIM, as_path=REAL)
    lab.check("C11 the real route validates on both axes",
              r.origin_state == "valid" and r.path_state == "valid", str(r))
    lab.check("C11 it arrived as a signed BGPsec path", r.signed, str(r))

    growth = lab.signature_growth(seconds=25)
    for label, hops, sigs in growth:
        lab.check(f"C11 {label}: {sigs} signature(s) for {hops} hop(s)",
                  hops == sigs and sigs > 0, f"{hops} hops, {sigs} signatures")
    counts = [s for _, _, s in growth]
    lab.check("C11 the signature block grows by one at every hop",
              counts == sorted(counts) and counts == list(range(1, len(counts) + 1)),
              f"signatures per link, origin outwards: {counts}")

    lab.attack("forge")
    forged = lab.wait_for_route(lab.VICTIM, via=lab.ATTACKER_PEER, timeout=150)
    lab.check("C12 the forged path is rated Invalid on the path axis",
              forged.path_state == "invalid", str(forged))
    lab.check("C12 ROV is still fooled — the origin axis still says valid",
              forged.origin_state == "valid", str(forged))
    lab.check("C12 the route is dropped by policy, not merely out-preferred",
              forged.ignored and not forged.best, str(forged))
    r = lab.best(lab.VICTIM)
    lab.check("C12 AS64666 could not forge AS64602's signature, so the real route wins",
              r.as_path == REAL, str(r))
    lab.check("C12 the winning route carries a signature per hop, keyed by SKI",
              len(r.segments) == 3 and all(ski for _, ski in r.segments),
              ", ".join(f"AS{a}:{s[:8]}…" for a, s in r.segments))

    # C13 — revocation. Nothing on any router changes; the CA withdraws its
    # statement about AS64602's key and the route stops verifying.
    lab.attack("stop")
    lab.revoke_router_key(64602)
    after = lab.routes(lab.VICTIM)
    lab.check("C13 revoking the certificate stops the route verifying",
              not any(x.path_state == "valid" for x in after),
              "; ".join(str(x) for x in after) or "no path at all")
    lab.restore_router_key(64602)
    r = lab.wait_for_best(lab.VICTIM, as_path=REAL, timeout=180)
    lab.check("C13 re-issuing the certificate restores it",
              r.path_state == "valid", str(r))
    lab.checkpoint("Part C")


def part_d():
    lab.set_part("d")
    lab.attack("stop")

    r = lab.wait_for_best(lab.VICTIM, as_path=REAL, timeout=150)
    lab.check("D15 the route still arrives — a non-BGPsec AS is not cut off",
              r.as_path == REAL, str(r))
    lab.check("D15 but it can no longer be verified: path Invalid, de-preferred",
              r.path_state == "invalid" and r.localpref <= 100, str(r))
    obs = lab.wait_for_best(lab.OBSERVER)
    lab.check("D15 AS64605 can prove the origin and nothing about the path",
              obs.origin_state == "valid" and not obs.signed, str(obs))
    lab.checkpoint("Part D")


PARTS = {"a": part_a, "b": part_b, "c": part_c, "d": part_d}

if __name__ == "__main__":
    wanted = sys.argv[1:] or list(PARTS)
    start = time.time()
    for key in wanted:
        print(f"\n{'=' * 62}\n  PART {key.upper()}\n{'=' * 62}")
        PARTS[key]()
    print(f"\nsmoke test finished in {(time.time() - start) / 60:.1f} min")
