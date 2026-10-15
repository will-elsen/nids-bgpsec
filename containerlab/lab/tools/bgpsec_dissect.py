"""Dissect BGPsec_PATH attributes (RFC 8205) out of a pcap.

Usage: python3 bgpsec_dissect.py <file.pcap>

Scans raw pcap bytes for BGP messages (16-byte 0xFF marker), parses UPDATE
path attributes, and for each BGPsec_PATH (type 33) prints the Secure_Path
AS chain and every signature segment's SKI and length. No tshark needed.
"""
import struct, sys

MARKER = b'\xff' * 16

def parse_bgpsec_path(attr):
    sp_len = struct.unpack('!H', attr[0:2])[0]
    hops = []
    off = 2
    while off < sp_len:                       # Secure_Path segments: pCount(1) flags(1) AS(4)
        pcount, flags = attr[off], attr[off + 1]
        asn = struct.unpack('!I', attr[off + 2:off + 6])[0]
        hops.append((asn, pcount, flags))
        off += 6
    sigs = []
    while off < len(attr):                    # Signature_Blocks: len(2) algo(1) segments...
        blk_len, algo = struct.unpack('!H', attr[off:off + 2])[0], attr[off + 2]
        blk_end = off + blk_len
        off += 3
        while off < blk_end:                  # segments: SKI(20) sig_len(2) sig(var)
            ski = attr[off:off + 20].hex().upper()
            sig_len = struct.unpack('!H', attr[off + 20:off + 22])[0]
            sigs.append((algo, ski, sig_len))
            off += 22 + sig_len
        off = blk_end
    return hops, sigs

def main(path):
    data = open(path, 'rb').read()
    n_update = 0
    pos = 0
    while (i := data.find(MARKER, pos)) != -1:
        pos = i + 1
        if i + 19 > len(data):
            break
        mlen, mtype = struct.unpack('!HB', data[i + 16:i + 19])
        if mtype != 2 or not 23 <= mlen <= 4096 or i + mlen > len(data):
            continue                          # not a plausible UPDATE
        msg = data[i:i + mlen]
        wlen = struct.unpack('!H', msg[19:21])[0]
        ap = 21 + wlen
        alen = struct.unpack('!H', msg[ap:ap + 2])[0]
        attrs, aend = ap + 2, ap + 2 + alen
        n_update += 1
        while attrs < aend:
            flags, atype = msg[attrs], msg[attrs + 1]
            if flags & 0x10:
                l = struct.unpack('!H', msg[attrs + 2:attrs + 4])[0]
                body = msg[attrs + 4:attrs + 4 + l]
                attrs += 4 + l
            else:
                l = msg[attrs + 2]
                body = msg[attrs + 3:attrs + 3 + l]
                attrs += 3 + l
            if atype != 33:
                continue
            hops, sigs = parse_bgpsec_path(body)
            path_str = ' '.join(f'AS{a}' + (f'(pCount={p})' if p != 1 else '')
                                for a, p, _ in hops)
            print(f'UPDATE #{n_update} (offset {i}): BGPsec_PATH')
            print(f'  Secure_Path ({len(hops)} hops): {path_str}')
            print(f'  Signature segments: {len(sigs)}')
            for algo, ski, sl in sigs:
                print(f'    algo {algo}  SKI {ski}  sig {sl}B')
            print(f'  hops == signatures: {"OK" if len(hops) == len(sigs) else "MISMATCH"}')
    if n_update == 0:
        print('no BGP UPDATE messages found')

if __name__ == '__main__':
    main(sys.argv[1])
