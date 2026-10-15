#!/bin/bash

# Copyright (c) 2025 SIDN Labs
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its
#    contributors may be used to endorse or promote products derived from
#    this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

set -e

while read -r item; do
	asn=$(awk -F '-' '{print $1}' <<< "$item")
	SKI=$(awk '{print $2}' <<< "$item")

	asn_hex="$(printf '%08X' "$asn")"	

	# add CSR to Krill
	dir2=${SKI:0:2}
	dir4=${SKI:2:4}
	part_SKI=${SKI:6}
	cd /var/lib/bgpsec-keys/"$dir2"/"$dir4"
	krillc bgpsec add --asn "$asn" --csr "$part_SKI".csr -t a_random_admin_token -c testbed -s http://10.0.0.10:3000/
     	
    # wait for file to be generated
	sleep 1
	# copy signed certificate to /var/lib/bgpsec-keys
	cp /var/krill/data/repo/rsync/current/testbed/0/ROUTER-"$asn_hex"-"$SKI".cer /var/lib/bgpsec-keys/"$dir2"/"$dir4"/"$part_SKI".cert

	# make root owner of private keys so that it is accessible to the routers running as root
	chown root:root /var/lib/bgpsec-keys/"$dir2"/"$dir4"/"$part_SKI".der

	# output AS - SKI pairs
	echo "Added certificate for AS$asn with SKI $SKI to Krill."
done < /var/lib/bgpsec-keys/ski-list.txt



