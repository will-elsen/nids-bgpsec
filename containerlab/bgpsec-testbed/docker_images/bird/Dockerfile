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

# First stage: Building bird
ARG IMAGE=ubuntu:24.04
FROM $IMAGE AS build

ARG BIRD_BGPSEC_REPO=https://github.com/securerouting/bird.git
ARG BIRD_BGPSEC_BRANCH="1.6.0-bgpsec-0.9"
ARG BIRD_PROTOCOLS="bgp,pipe,radv,static"

# Install dependencies
RUN apt update && apt install -y git build-essential autoconf flex bison libssl3 libreadline6-dev libssl-dev

# Setup build environment
RUN mkdir -p /build/installroot
WORKDIR "/build/"

# Checkout bgpsec branch
RUN git clone $BIRD_BGPSEC_REPO && \
    cd bird && \
    git checkout -b $BIRD_BGPSEC_BRANCH

# Apply patches
ADD patches/bird-bgpsec-fixes.patch /build/bird
ADD patches/bird-bgpsec-cap-fix.patch /build/bird

RUN cd bird && \
    git apply --ignore-space-change --ignore-whitespace bird-bgpsec-fixes.patch && \
    git apply --ignore-space-change --ignore-whitespace bird-bgpsec-cap-fix.patch

# Build bird/ipv6
RUN cd bird && \
    autoconf && \
    ./configure --enable-ipv6 --enable-bgpsec --with-protocols=$BIRD_PROTOCOLS && \
    make  -j && \
    make install DESTDIR=/build/installroot && \
    make clean 

# Build bird/ipv4
RUN cd bird && \
    ./configure --enable-bgpsec --with-protocols=$BIRD_PROTOCOLS && \
    make  -j && \
    make install DESTDIR=/build/installroot

RUN cd /build/installroot && tar -cf /build/artifact.tar -C /build/installroot . 


# Second stage: only required binaries, configs and scripts
FROM $IMAGE AS deploy

# Install dependencies
RUN apt-get update && \
    apt-get -y dist-upgrade && \
    apt-get install -y --no-install-recommends openssl libreadline-dev && \
    apt-get clean

# Copy over relevant files from build stage, and 'install' them
COPY --from=build /build/artifact.tar /build/
RUN tar -xvf /build/artifact.tar -C / && rm -rf /build

CMD ["bird", "-d", "-f", "-c", "/etc/bird.conf"]
