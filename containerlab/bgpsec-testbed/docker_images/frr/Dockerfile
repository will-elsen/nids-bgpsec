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

# First stage: Install libyang, RTRlib and FRR
ARG IMAGE=ubuntu:24.04
FROM $IMAGE AS build

# install required packages
RUN apt-get update && apt-get install -y git autogen cmake libpcre2-dev autoconf libtool libjson-c-dev libelf-dev libreadline6-dev python3-dev build-essential libpcre3-dev libssl-dev libxml2-dev pkg-config libcap-dev flex bison libcap2-bin frr-rpki-rtrlib 

# Setup build environment
RUN mkdir -p /build/installroot
WORKDIR "/build/"

# Clone and build libyang for frr compilation
RUN git clone https://github.com/CESNET/libyang.git && \
    cd libyang && \
    git checkout v2.1.4 && \
    mkdir build && cd build && \
    cmake .. && \
    make -j && \
    # install for compilation of frr
    make install && \
    # install for use in second stage
    make install DESTDIR=/build/installroot

# Clone and build RTRLIB
RUN git clone https://github.com/rtrlib/rtrlib.git && \
    cd rtrlib && \
    git checkout 41f5f057d4762267fbd6224c672bc439570f944d && \
    mkdir build && cd build && \
    cmake -D CMAKE_BUILD_TYPE=Release -D WITH_BGPSEC=Yes ../ && \
    make -j && \
    # install for compilation of frr
    make install && \
    # install for use in second stage
    make install DESTDIR=/build/installroot

# Clone and build frrbgpsec branch
RUN git clone https://github.com/colinbs/frr.git && \
    cd frr && \
    git checkout frrbgpsec && \
    ./bootstrap.sh && \ 
    ./configure --enable-rpki && \
    make -j && \
    make install DESTDIR=/build/installroot

RUN cd /build/installroot && tar -cf /build/artifact.tar -C /build/installroot . 


# Second stage: only required binaries, configs and scripts
FROM $IMAGE AS deploy

# Install dependencies
RUN apt-get update && \
    apt-get -y dist-upgrade && \
    apt-get install -y --no-install-recommends libjson-c-dev frr-rpki-rtrlib && \
    apt-get clean

# Copy over relevant files from build stage, and 'install' them
COPY --from=build /build/artifact.tar /build/
RUN tar -xvf /build/artifact.tar -C / && \
    rm -rf /build && \
    echo include /usr/local/lib >> /etc/ld.so.conf && \
    ldconfig

# start up the bgp daemon
CMD ["bgpd", "-u", "root", "-g", "root", "--log", "stdout", "--log-level", "debug", "-M", "rpki"]
