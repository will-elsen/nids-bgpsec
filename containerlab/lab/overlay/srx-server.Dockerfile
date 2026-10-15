# Makes the SRx validation engine restartable in place.
#
# srx_server keeps a client table keyed by proxy ID, and an entry outlives the
# router that made it. Every part switch in the curriculum restarts all five
# QuaggaSRx routers, and a router coming back up against its own stale mapping
# never completes the handshake — bgpd logs `isConnected (bgp->srxProxy): 0`
# after a 30s `initUnSocket` timeout, every validation result comes back
# `undefined`, and the router then drops the route because
# `srx policy origin ignore undefined` is on by default. The lab appears to
# deploy and then quietly has no routes. Measured 2026-07-31: with five
# routers restarting at once, one loses this race most times.
#
# So srx_server gets the same supervisor as the routers, and set_part.sh
# restarts it first — a clean client table, then routers registering into it.
ARG BASE=bgpsec/srx-server:upstream
FROM $BASE

COPY run-daemon.sh /usr/local/bin/run-daemon.sh
RUN chmod +x /usr/local/bin/run-daemon.sh

ENTRYPOINT ["/usr/local/bin/run-daemon.sh"]
CMD ["srx_server", "-f", "/etc/srx_server.conf"]
