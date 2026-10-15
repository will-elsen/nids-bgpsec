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

# First stage: Building srx-crypto-api and preparing exabgpsrx
ARG IMAGE=ubuntu:24.04
FROM $IMAGE AS build

RUN apt-get update && apt-get install -y git libconfig-dev uthash-dev build-essential libssl-dev automake python3

# Setup build environment
RUN mkdir -p /build/installroot/opt
WORKDIR "/build/"

# clone and install srx-crypto-api
RUN git clone https://github.com/usnistgov/NIST-BGP-SRx.git && \
    cd NIST-BGP-SRx/srx-crypto-api && \
    ./configure CFLAGS="-O0 -g" && \
    make -j && \
    make install DESTDIR=/build/installroot

WORKDIR "/build/installroot/opt"
# clone and setup exabgp
RUN git clone https://github.com/usnistgov/exabgpsrx.git

# update six.py in exabgpsrx
ADD patches/small_fixes_packages.patch /build/installroot/opt/exabgpsrx
RUN cd exabgpsrx && \
    git apply --ignore-space-change --ignore-whitespace small_fixes_packages.patch

RUN exabgpsrx/sbin/exabgp --fi > exabgpsrx/etc/exabgp/exabgp.env \
    && mkfifo exabgpsrx/run/exabgp.in \
    && mkfifo exabgpsrx/run/exabgp.out \
    && chmod 660 exabgpsrx/run/exabgp.in \
    && chmod 660 exabgpsrx/run/exabgp.out

RUN cd /build/installroot && tar -cf /build/artifact.tar -C /build/installroot .


# Second stage: only required binaries, configs and scripts
FROM $IMAGE AS deploy

# Install dependencies
RUN apt-get update && \
    apt-get -y dist-upgrade && \
    apt-get install -y --no-install-recommends python3 libconfig-dev && \
    apt-get clean

# Copy over relevant files from build stage, and 'install' them
COPY --from=build /build/artifact.tar /build/
RUN tar -xvf /build/artifact.tar -C / && rm -rf /build

COPY entrypoint.sh /opt/entrypoint.sh

# run exabgp
ENTRYPOINT ["/opt/entrypoint.sh"]
CMD ["env", "exabgp.daemon.user=root", "/opt/exabgpsrx/sbin/exabgp", "/etc/exabgp.conf", "--debug"]
