# Adds packet capture to the upstream GoBGP-SRx image. See quaggasrx.Dockerfile
# for why tcpdump is baked in rather than run from the host namespace.
ARG BASE=bgpsec/gobgpsrx:upstream
FROM $BASE

RUN apt-get update && \
    apt-get install -y --no-install-recommends tcpdump iproute2 iputils-ping procps && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

COPY run-daemon.sh /usr/local/bin/run-daemon.sh
RUN chmod +x /usr/local/bin/run-daemon.sh

# Same supervisor as the QuaggaSRx image: `pkill -x gobgpd` reloads the
# observer against an edited config without recreating the container.
ENTRYPOINT ["/usr/local/bin/run-daemon.sh", "gobgpd"]
CMD ["-p", "-f", "/etc/gobgpd.conf", "--log-level=debug"]
