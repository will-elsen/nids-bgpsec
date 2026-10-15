# Lab-owned router keys

BGPsec router private keys for the two ASes this lab adds to the vendored
testbed: **AS64601** (second transit) and **AS64666** (the attacker). They are
test material for a self-contained, containerized RPKI with its own CA — they
carry no real-world trust, which is why they can live in the repo like the
testbed's four in `bgpsec-testbed/key_setup/bird_testbed_keys/`.

Format is the same as the testbed's: a DER-encoded EC P-256 private key named
`<asn>.<SKI>.key`, where the SKI is the SHA-1 of the public key.
`tools/build_vault.sh` assembles `phase4/keys/` (the vault every router
bind-mounts) from these two plus the vendored four, and checks that each
file's name matches its key.

To rotate one: generate a new key, name it by its SKI, delete the old file,
run `tools/build_vault.sh --force`, then `python3 tools/gen_configs.py phase4`
so the router configs pick up the new SKI.

```bash
openssl ecparam -genkey -name prime256v1 -noout -out k.pem
openssl ec -in k.pem -outform DER -out k.der
SKI=$(openssl ec -in k.pem -pubout | openssl asn1parse -strparse 23 -noout -out - \
      | openssl dgst -sha1 | awk '{print toupper($NF)}')
mv k.der <asn>.$SKI.key && rm k.pem
```
