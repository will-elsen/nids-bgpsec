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

# First stage: Building srx-crypto-api and gobgpsrx
ARG IMAGE=ubuntu:24.04
FROM $IMAGE AS build

RUN apt-get update && \
    apt-get install -y --no-install-recommends git libconfig-dev uthash-dev build-essential wget libssl-dev automake ca-certificates

# Setup build environment
RUN mkdir -p /build/installroot/usr/local/go/bin
WORKDIR "/build/"

# clone and install srx-crypto-api
RUN git clone https://github.com/usnistgov/NIST-BGP-SRx.git && \
    cd NIST-BGP-SRx/srx-crypto-api && \
    ./configure --prefix=/build/installroot/usr/local CFLAGS="-O0 -g" && \
    make -j && \
    make install && \
    make clean

# install go
RUN wget https://go.dev/dl/go1.23.5.linux-amd64.tar.gz && tar -C /usr/local -xzf go1.23.5.linux-amd64.tar.gz && rm go1.23.5.linux-amd64.tar.gz
ENV PATH="$PATH:/usr/local/go/bin:/root/go/bin"
RUN go install google.golang.org/protobuf/cmd/protoc-gen-go@latest && go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@latest

# install gobgpsrx
ENV CGO_LDFLAGS="-L/build/installroot/usr/local/lib64/srx/ -Wl,-rpath -Wl,/build/installroot/usr/local/lib64/srx/" CGO_CFLAGS="-I/build/installroot/usr/local/include/srx/"
RUN git clone https://github.com/usnistgov/gobgpsrx.git && \
    cd gobgpsrx && \
    go build -o /build/installroot/usr/local/go/bin ./...

# prepare for deploy image
RUN cd /build/installroot && tar -cf /build/artifact.tar -C /build/installroot . 


# Second stage: only required binaries, configs and scripts
FROM $IMAGE AS deploy

# Install dependencies
RUN apt-get update && apt-get -y dist-upgrade && \
    apt-get install -y --no-install-recommends libconfig-dev && \
    apt-get clean

# Copy over relevant files from build stage, and 'install' them
COPY --from=build /build/artifact.tar /build/
RUN tar -xf /build/artifact.tar -C / && \
    rm -rf /build

ENV PATH="$PATH:/usr/local/go/bin" LD_LIBRARY_PATH="/usr/local/lib64/srx" 

# run gobgpd
ENTRYPOINT ["gobgpd"]
CMD ["-p", "-f", "/etc/gobgpd.conf", "--log-level=debug"]