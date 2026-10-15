"""Minimal RTR (RFC 8210 v1) client: Reset Query, dump every PDU until End of Data."""
import socket, struct, sys

HOST, PORT = sys.argv[1], int(sys.argv[2])
NAMES = {0: 'Serial Notify', 1: 'Serial Query', 2: 'Reset Query', 3: 'Cache Response',
         4: 'IPv4 Prefix', 6: 'IPv6 Prefix', 7: 'End of Data', 8: 'Cache Reset',
         9: 'Router Key', 10: 'Error Report'}

s = socket.create_connection((HOST, PORT), timeout=10)
s.sendall(struct.pack('!BBHI', 1, 2, 0, 8))  # v1 Reset Query

def read_exact(n):
    buf = b''
    while len(buf) < n:
        chunk = s.recv(n - len(buf))
        if not chunk:
            raise ConnectionError('EOF')
        buf += chunk
    return buf

counts = {}
while True:
    ver, ptype, sess, length = struct.unpack('!BBHI', read_exact(8))
    body = read_exact(length - 8)
    counts[ptype] = counts.get(ptype, 0) + 1
    name = NAMES.get(ptype, f'type {ptype}')
    if ptype == 9:  # Router Key: flags live in the header; body = SKI(20) ASN(4) SPKI(rest)
        ski = body[0:20].hex().upper()
        asn = struct.unpack('!I', body[20:24])[0]
        print(f'PDU {name:14} AS{asn}  SKI {ski}  SPKI {len(body)-26}B')
    elif ptype in (4, 6):
        flags, plen, maxlen, _ = body[0], body[1], body[2], body[3]
        addr = socket.inet_ntop(socket.AF_INET if ptype == 4 else socket.AF_INET6,
                                body[4:8] if ptype == 4 else body[4:20])
        asn = struct.unpack('!I', body[-4:])[0]
        print(f'PDU {name:14} {addr}/{plen}-{maxlen} => AS{asn} (announce={flags & 1})')
    else:
        print(f'PDU {name:14} session={sess} len={length}')
    if ptype == 7:
        serial = struct.unpack('!I', body[:4])[0]
        print(f'--- End of Data, serial {serial}. PDU counts: '
              + ', '.join(f'{NAMES.get(t, t)}={n}' for t, n in sorted(counts.items())))
        break
s.close()
