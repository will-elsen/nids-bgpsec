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


# This scripts creates private keys and certificate signing requests. It then determines the matching SKI to create the directory structure required by 
# the NIST-BGP-SRx suite and adds the SKI to the (priv-)ski-list.txt (folder `testbed_keys`). 
# It also generates a folder containing the naming structure required by BIRD (folder `bird_testbed_keys`).
# CSRs are signed with a private CA certificate. In a topology that runs a Krill-based testbed these certificates will be overwritten with certificates signed through Krill.
# It takes a file with a list of ASNs as an argument (one ASN per line).

# exit if one command fails
set -e

# set required variables
if [ $# -eq 0 ]; then
 echo "Please provide a file with ASNs."
 exit 1
fi

# create private key and certificate for later signing
openssl ecparam -name prime256v1 -genkey -out ca.pem
openssl req -new -x509 -key ca.pem -out ca.cert -days 3650 -sha256 -subj "/CN=local"

# create folder for keys in NIST-BGP-SRx and BIRD structure
mkdir -p testbed_keys
mkdir -p bird_testbed_keys/bgpsec-keys
mkdir -p bird_testbed_keys/bgpsec-private-keys

while read -r asn; do
	# create signing request for new ASN
	openssl ecparam -genkey -name prime256v1 -out as"$asn"_bgpsec.pem

	# create common name based on ASN
	asn_hex="$(printf '0000%04X' "$asn")"
	SUBJ="/CN=ROUTER-$asn_hex"
    openssl req -new -key as"$asn"_bgpsec.pem -out as"$asn"_bgpsec.csr --config bgpsec_openssl.cnf -subj "$SUBJ"
	openssl req -inform PEM -outform DER -in as"$asn"_bgpsec.csr -out as"$asn"_bgpsec_der.csr

	# create public key 
	openssl ec -in as"$asn"_bgpsec.pem -pubout -out as"$asn"_bgpsec.key
	
	# generate SKI using public key
	SKI=$(openssl asn1parse -in as"$asn"_bgpsec.key -strparse 23 -noout -out - | openssl dgst -sha1 | awk '{print toupper($2)}')
	
	# create testbed_keys folder for certificate and private key in the format required by NIST-BGP-SRx
	dir2=${SKI:0:2}
	dir4=${SKI:2:4}
	part_SKI=${SKI:6}
	mkdir -p testbed_keys/"$dir2"/"$dir4"
	
	# make private and public key der format
	openssl ec -inform pem -in as"$asn"_bgpsec.pem -outform der -out "$part_SKI".der
	openssl pkey -pubin -in as"$asn"_bgpsec.key -outform DER -pubout -out "$asn"."$SKI".0.key

	# sign csr with private CA
	openssl x509 -req -in as"$asn"_bgpsec.csr -CA ca.cert -CAkey ca.pem -out "$part_SKI"_pem.cert -days 365 -sha256
	openssl x509 -outform der -in "$part_SKI"_pem.cert -out "$part_SKI".cert 
	
	# move files to folders and add to (priv-)ski-list.txt
	cp "$part_SKI".der testbed_keys/"$dir2"/"$dir4"/
	mv as"$asn"_bgpsec_der.csr testbed_keys/"$dir2"/"$dir4"/"$part_SKI".csr   
	mv "$part_SKI".cert testbed_keys/"$dir2"/"$dir4"
	echo "$asn-SKI: $SKI" | tee -a testbed_keys/priv-ski-list.txt > /dev/null
	echo "$asn-SKI: $SKI" | tee -a testbed_keys/ski-list.txt > /dev/null 

    # move files to folders in bird directory structure
	mv "$part_SKI".der bird_testbed_keys/bgpsec-private-keys/"$asn"."$SKI".key
	mv "$asn"."$SKI".0.key bird_testbed_keys/bgpsec-keys

	# Add SKI to configuration files that come with the testbed and are required for the topologies
	# ASN 64602
	if [ "$asn" -eq 64602 ]; then
		# bird
		sed -i 's/bgpsec_ski \"[^\"]*\"/bgpsec_ski \"'"$SKI"'\"/' ../topologies/configs/bird/bird_as64602.conf
		# exabgpsrx
		sed -i 's/\(ski \)[^;]*;/\1'"$SKI"';/'  ../topologies/configs/exabgpsrx/exabgp-as64602.conf
		# frr
		new_path="/$dir2/$dir4/$part_SKI.der"
		sed -i -e 's|\(bgpsec privkey /var/lib/bgpsec-keys\)[^ ]*|\1'"$new_path"'|' -e 's/\(bgpsec privkey ski \)[^ ]*/\1'"$SKI"'/' ../topologies/configs/frr/bgpd_as64602.conf
		# gobgpsrx
		sed -i 's/SKI = \"[^\"]*\"/SKI = \"'"$SKI"'\"/' ../topologies/configs/gobgpsrx/gobgpd-as64602.conf
		# quaggasrx
		sed -i 's/\(srx bgpsec ski 0 1 \)[^ ]*/\1'"$SKI"'/' ../topologies/configs/quaggasrx/quagga_as64602.conf
	# ASN 64603
	elif [ "$asn" -eq 64603 ]; then
		# bird
		sed -i 's/bgpsec_ski \"[^\"]*\"/bgpsec_ski \"'"$SKI"'\"/' ../topologies/configs/bird/bird_as64603.conf
		# exabgpsrx
		sed -i 's/\(ski \)[^;]*;/\1'"$SKI"';/'  ../topologies/configs/exabgpsrx/exabgp-as64603.conf
		# frr
		new_path="/$dir2/$dir4/$part_SKI.der"
		sed -i -e 's|\(bgpsec privkey /var/lib/bgpsec-keys\)[^ ]*|\1'"$new_path"'|' -e 's/\(bgpsec privkey ski \)[^ ]*/\1'"$SKI"'/' ../topologies/configs/frr/bgpd_as64603*.conf
		# gobgpsrx 
		sed -i 's/SKI = \"[^\"]*\"/SKI = \"'"$SKI"'\"/' ../topologies/configs/gobgpsrx/gobgpd-as64603.conf
		# quaggasrx
		sed -i 's/\(srx bgpsec ski 0 1 \)[^ ]*/\1'"$SKI"'/' ../topologies/configs/quaggasrx/quagga_as64603.conf
	# ASN 64604
	elif [ "$asn" -eq 64604 ]; then
		# quaggasrx
		sed -i 's/\(srx bgpsec ski 0 1 \)[^ ]*/\1'"$SKI"'/' ../topologies/configs/quaggasrx/quagga_as64604_4routers.conf
	# ASN 64605
	elif [ "$asn" -eq 64605 ]; then
		# gobgpsrx 
		sed -i 's/SKI = \"[^\"]*\"/SKI = \"'"$SKI"'\"/' ../topologies/configs/gobgpsrx/gobgpd-as64605_4routers.conf
	fi
done < "$1"

printf "The following ASN-SKI pairs were created. All configuration files necessary for the testbed topologies were adapted.\nIn case further configuration files were added, please update the SKIs manually.\n"
cat testbed_keys/ski-list.txt

# remove csr and key from current dir
rm ./*_bgpsec.pem ./*_bgpsec.csr ./*_bgpsec.key ./*_pem.cert

