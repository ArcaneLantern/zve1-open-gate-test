import struct, sys
d = {l.split()[1]: (int(l.split()[2], 16), bytes.fromhex(l.split()[3])) for l in open(sys.argv[1]) if l.startswith('data ')}
at = lambda a, f='<I': next(struct.unpack_from(f, b, a - base)[0] for base, b in d.values() if base <= a < base + len(b))
print('byte 0x19967A7 (override del intervalo):', hex(at(0x19967a7, '<B')), '| bytes 19967A0..AF:', d['debug_byte'][1].hex(' '))
for c in range(4):
    a = 0x1a08998 + 16 * c; b = d['interval_tab'][1][a - 0x1a08900:a - 0x1a08900 + 16]
    print(f'categoria {c}: A(u8)={b[0]},{b[1]}  B(u8)={b[2]},{b[3]}  C(u16)={struct.unpack_from("<2H", b, 4)}  D(u16)={struct.unpack_from("<2H", b, 8)}  resto={b[12:].hex()}')
S = 0x15b5d70
for n, o, f in (('drive_mode', 0x138, '<I'), ('burst_count_max', 0x120, '<I'), ('+0x124', 0x124, '<I'), ('+0x128', 0x128, '<I'), ('+0x140', 0x140, '<I')):
    print(f'estado {n}: {at(S + o, f)}')
print('customFps HiPlus/Hi/Mid/Lo:', [at(S + 0x12c + i, '<B') for i in range(4)])
T = 0x197deec
print('temporizador: handle', hex(at(T)), '| flags', at(T + 4, '<H'), '| contador', at(T + 8), '| objetivo', at(T + 12), '| periodo_ms', at(T + 16), '| modo preciso', at(T + 20, '<B'))
