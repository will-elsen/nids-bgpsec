#!/bin/bash

# copy keys from temp directory
cp -r /var/lib/bgpsec-keys-temp /var/lib/bgpsec-keys
# modify permissions of the copied keys private keys to make them accessible for exabgpsrx running as nobody
find /var/lib/bgpsec-keys -name *.der -exec chown nobody: {} \;

# execute CMD
exec "$@"