#!/usr/bin/env bash
# Build the lab's key vault, phase4/keys/, from the private keys in the repo.
#
#   build_vault.sh [phase4-dir] [--force]
#
# Every router, plus Krill and krillc, bind-mounts the vault at
# /var/lib/bgpsec-keys. The vault is not committed — sign_csr.sh rewrites
# its certificates on every deploy and chowns the private keys to root — so
# it is rebuilt from the private keys that are:
#
#   bgpsec-testbed/key_setup/bird_testbed_keys/bgpsec-private-keys/
#       AS64602-AS64605, vendored from SIDN's testbed
#   lab/router_keys/
#       AS64601 and AS64666, the two ASes this lab adds
#
# Both hold DER EC P-256 private keys named <asn>.<SKI>.key. Everything else
# in the vault is derived from them with openssl: the NIST-BGP-SRx layout
# (<SKI[0:2]>/<SKI[2:6]>/<SKI[6:]>.{der,csr,cert}), a CSR per key for krillc
# to submit, a placeholder certificate signed by the vendored lab CA (Krill
# replaces it at deploy), and the two SKI lists. Same keys in, same SKIs
# out — which is what keeps the generated configs in phase4/configs/ valid
# on every machine.
#
# Idempotent: a vault that already holds every key is left alone. --force
# rebuilds it (the next deploy re-signs the placeholder certificates). A
# vault being replaced is moved aside to keys.bak.<timestamp>/, never deleted.
#
# labkit.deploy() runs this automatically, and so does the Codespace
# bootstrap, so a fresh clone has no manual step.
set -euo pipefail

# Git-for-Windows shim: keep MSYS from rewriting "/CN=..." as a Windows path.
export MSYS2_ARG_CONV_EXCL="/CN="

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAB="$(dirname "$HERE")"
PHASE4="$LAB/phase4"
FORCE=0
for arg in "$@"; do
    case "$arg" in
        --force)   FORCE=1 ;;
        -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
        *)         PHASE4="$(cd "$arg" && pwd)" ;;
    esac
done
VAULT="$PHASE4/keys"
KEY_SETUP="$LAB/../bgpsec-testbed/key_setup"
SOURCES=("$KEY_SETUP/bird_testbed_keys/bgpsec-private-keys" "$LAB/router_keys")

command -v openssl >/dev/null 2>&1 ||
    { echo "build_vault.sh: openssl not found — install it (Debian/Ubuntu: apt-get install openssl)" >&2; exit 1; }
[ -f "$KEY_SETUP/ca.pem" ] && [ -f "$KEY_SETUP/ca.cert" ] ||
    { echo "build_vault.sh: lab CA (ca.pem/ca.cert) missing from $KEY_SETUP" >&2; exit 1; }

# --- the keys ---------------------------------------------------------------
keys=()
for dir in "${SOURCES[@]}"; do
    for f in "$dir"/*.key; do
        [ -e "$f" ] && keys+=("$f")
    done
done
[ "${#keys[@]}" -gt 0 ] || { echo "build_vault.sh: no <asn>.<SKI>.key files found" >&2; exit 1; }

# SKI = SHA-1 of the public key BIT STRING; offset 23 skips the SPKI header.
# The same computation as the testbed's create_certificates.sh.
ski_of() {
    openssl ec -inform DER -in "$1" -pubout 2>/dev/null |
        openssl asn1parse -strparse 23 -noout -out - |
        openssl dgst -sha1 | awk '{print toupper($NF)}'
}

# --- already built? ---------------------------------------------------------
if [ "$FORCE" -eq 0 ] && [ -f "$VAULT/ski-list.txt" ]; then
    complete=1
    for f in "${keys[@]}"; do
        b="$(basename "$f" .key)"; asn="${b%%.*}"; ski="${b#*.}"
        grep -q "^$asn-SKI: $ski\$" "$VAULT/ski-list.txt" &&
            [ -f "$VAULT/${ski:0:2}/${ski:2:4}/${ski:6}.der" ] || complete=0
    done
    if [ "$complete" -eq 1 ]; then
        echo "key vault already built: $VAULT ($(wc -l < "$VAULT/ski-list.txt" | tr -d ' ') keys)"
        exit 0
    fi
fi

# --- (re)build --------------------------------------------------------------
if [ -d "$VAULT" ]; then
    # Its contents may be root-owned after a deploy; a rename needs only the
    # parent directory, and keeps whatever keys were there.
    bak="$VAULT.bak.$(date +%Y%m%d%H%M%S)"
    mv "$VAULT" "$bak"
    echo "previous vault moved to $bak"
fi
mkdir -p "$VAULT"
cp "$KEY_SETUP/ca.pem" "$KEY_SETUP/ca.cert" "$VAULT/"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
# CSR extensions per RFC 8209: keyUsage digitalSignature and the BGPsec
# router EKU, id-kp-bgpsec-router (1.3.6.1.5.5.7.3.30). Spelled out as a
# minimal config so it works with OpenSSL 1.1 as well as 3.x — the testbed's
# bgpsec_openssl.cnf produces the same request but needs 3.x.
cat > "$tmp/req.cnf" <<'CNF'
[req]
distinguished_name = dn
req_extensions = v3_req
[dn]
[v3_req]
keyUsage = digitalSignature
extendedKeyUsage = 1.3.6.1.5.5.7.3.30
CNF

: > "$VAULT/ski-list.txt"
: > "$VAULT/priv-ski-list.txt"
for f in "${keys[@]}"; do
    b="$(basename "$f" .key)"; asn="${b%%.*}"; ski="${b#*.}"
    calc="$(ski_of "$f")"
    [ "$calc" = "$ski" ] ||
        { echo "build_vault.sh: $f is named for SKI $ski but its key has SKI $calc" >&2; exit 1; }
    dir="$VAULT/${ski:0:2}/${ski:2:4}"; part="${ski:6}"
    mkdir -p "$dir"
    cp "$f" "$dir/$part.der"
    # CN is the ASN as 8 hex digits, per RFC 8209 router certificate naming.
    openssl req -new -key "$f" -keyform DER -config "$tmp/req.cnf" \
        -subj "/CN=ROUTER-$(printf '0000%04X' "$asn")" -out "$tmp/$part.csr.pem" 2>/dev/null
    openssl req -in "$tmp/$part.csr.pem" -outform DER -out "$dir/$part.csr"
    openssl x509 -req -in "$tmp/$part.csr.pem" -CA "$VAULT/ca.cert" -CAkey "$VAULT/ca.pem" \
        -CAserial "$tmp/ca.srl" -CAcreateserial -days 365 -sha256 \
        -out "$tmp/$part.cert.pem" 2>/dev/null
    openssl x509 -in "$tmp/$part.cert.pem" -outform DER -out "$dir/$part.cert"
    echo "$asn-SKI: $ski" >> "$VAULT/ski-list.txt"
    echo "$asn-SKI: $ski" >> "$VAULT/priv-ski-list.txt"
done

echo "key vault built: $VAULT"
cat "$VAULT/ski-list.txt"

# The generated configs embed these SKIs; say so if they have drifted.
stale=0
for f in "${keys[@]}"; do
    b="$(basename "$f" .key)"; asn="${b%%.*}"; ski="${b#*.}"
    for conf in "$PHASE4"/configs/c/*as"$asn"*.conf; do
        if [ -e "$conf" ] && ! grep -q "$ski" "$conf"; then stale=1; fi
    done
done
[ "$stale" -eq 0 ] ||
    echo "WARNING: phase4/configs/ do not match these SKIs — run: python3 $HERE/gen_configs.py $PHASE4"
