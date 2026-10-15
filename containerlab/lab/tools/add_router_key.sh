#!/usr/bin/env bash
# Add a BGPsec router key + self-signed cert for one ASN to a key vault.
#
#   add_router_key.sh <vault-dir> <asn>
#
# Extracted from bgpsec-testbed/key_setup/create_certificates.sh — same openssl
# invocations, same NIST-BGP-SRx on-disk layout (<SKI[0:2]>/<SKI[2:6]>/<rest>),
# same ski-list.txt format. Differences, both deliberate:
#
#   * operates on a vault directory passed in, so the vendored testbed stays
#     untouched;
#   * does not rewrite any router config — upstream's version seds SKIs into
#     the testbed's own config files, which the lab does not use.
#
# The self-signed .cert here is a placeholder: krillc replaces it with a
# Krill-issued one at deploy time (sign_csr.sh iterates the vault's
# ski-list.txt, so a new ASN is picked up automatically).
#
# Requires ca.pem/ca.cert in the vault — copied from key_setup by the caller.
set -euo pipefail

VAULT="${1:?usage: add_router_key.sh <vault-dir> <asn>}"
ASN="${2:?usage: add_router_key.sh <vault-dir> <asn>}"
CNF="$(cd "$(dirname "$0")/../../bgpsec-testbed/key_setup" && pwd)/bgpsec_openssl.cnf"

cd "$VAULT"
[ -f ca.pem ] && [ -f ca.cert ] || { echo "no ca.pem/ca.cert in $VAULT" >&2; exit 1; }

if grep -q "^$ASN-SKI:" ski-list.txt 2>/dev/null; then
  echo "AS$ASN already in $VAULT/ski-list.txt — nothing to do"
  exit 0
fi

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

openssl ecparam -genkey -name prime256v1 -out "$tmp/key.pem" 2>/dev/null
# CN is the ASN as 8 hex digits, per RFC 8209 router certificate subject naming.
openssl req -new -key "$tmp/key.pem" -out "$tmp/req.csr" --config "$CNF" \
  -subj "/CN=ROUTER-$(printf '0000%04X' "$ASN")"
openssl req -inform PEM -outform DER -in "$tmp/req.csr" -out "$tmp/req_der.csr"
openssl ec -in "$tmp/key.pem" -pubout -out "$tmp/pub.key" 2>/dev/null

# SKI = SHA-1 of the public key BIT STRING; offset 23 skips the SPKI header.
SKI=$(openssl asn1parse -in "$tmp/pub.key" -strparse 23 -noout -out - \
      | openssl dgst -sha1 | awk '{print toupper($2)}')
dir2=${SKI:0:2}; dir4=${SKI:2:4}; part=${SKI:6}

openssl ec -inform pem -in "$tmp/key.pem" -outform der -out "$tmp/$part.der" 2>/dev/null
openssl x509 -req -in "$tmp/req.csr" -CA ca.cert -CAkey ca.pem \
  -out "$tmp/pem.cert" -days 365 -sha256 2>/dev/null
openssl x509 -outform der -in "$tmp/pem.cert" -out "$tmp/$part.cert"

mkdir -p "$dir2/$dir4"
cp "$tmp/$part.der"     "$dir2/$dir4/$part.der"
cp "$tmp/req_der.csr"   "$dir2/$dir4/$part.csr"
cp "$tmp/$part.cert"    "$dir2/$dir4/$part.cert"
echo "$ASN-SKI: $SKI" >> ski-list.txt
echo "$ASN-SKI: $SKI" >> priv-ski-list.txt

echo "$ASN-SKI: $SKI"
