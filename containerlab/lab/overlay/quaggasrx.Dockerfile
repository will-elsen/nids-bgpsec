# Adds packet capture and an in-place daemon restart to the upstream
# QuaggaSRx image.
#
# tcpdump lives in the router image so students can capture with
# `docker exec <node> tcpdump ...` instead of `ip netns exec`, which would
# require sudo and hang a Jupyter cell on an invisible password prompt.
#
# run-daemon.sh becomes PID 1 so `pkill -x bgpd` restarts bgpd against a
# freshly edited config without recreating the container (which would destroy
# the containerlab veths). See that script for the full reasoning — the short
# version is that BGPsec cannot be toggled on a live session, and the
# curriculum has to toggle it.
ARG BASE=bgpsec/quaggasrx:upstream
FROM $BASE

RUN apt-get update && \
    apt-get install -y --no-install-recommends tcpdump iproute2 iputils-ping procps && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

COPY run-daemon.sh /usr/local/bin/run-daemon.sh
RUN chmod +x /usr/local/bin/run-daemon.sh

ENTRYPOINT ["/usr/local/bin/run-daemon.sh"]
CMD ["bgpd", "-f", "/etc/quagga.conf"]
