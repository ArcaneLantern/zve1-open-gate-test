"""Burst rate from Sony ARW EXIF (stdlib only): DateTimeOriginal + SubSecTimeOriginal, grouped by gaps < 1 s."""
import struct, sys, glob, os, datetime
def exif(path):
    b = open(path, 'rb').read(512 * 1024)
    e = '<' if b[:2] == b'II' else '>'
    def ifd(o):
        out = {}
        for k in range(struct.unpack_from(e + 'H', b, o)[0]):
            t, ty, n, v = struct.unpack_from(e + 'HHII', b, o + 2 + 12 * k)
            size = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1, 10: 8}.get(ty, 1) * n
            at = o + 10 + 12 * k if size <= 4 else v
            if ty == 2: out[t] = b[at:at + n].split(b'\0')[0].decode('latin1')
            elif ty == 3: out[t] = struct.unpack_from(e + 'H', b, at)[0]
            elif ty == 5 and at + 8 <= len(b): out[t] = struct.unpack_from(e + 'II', b, at)
            else: out[t] = v
        return out
    i0 = ifd(struct.unpack_from(e + 'I', b, 4)[0]); ex = ifd(i0[0x8769])
    raw = ifd(i0[0x14a]) if 0x14a in i0 and i0[0x14a] + 2 < len(b) else {}
    t = datetime.datetime.strptime(ex[0x9003], '%Y:%m:%d %H:%M:%S')
    sub = ex.get(0x9291, '')
    t += datetime.timedelta(seconds=float('0.' + sub) if sub.strip().isdigit() else 0)
    sh = ex.get(0x829a)
    return t, len(sub.strip()), raw.get(0x103), raw.get(0x102), (sh[0] / sh[1] if isinstance(sh, tuple) and sh[1] else None), os.path.getsize(path)
shots = []
for f in glob.glob(sys.argv[1] + '/*/*.ARW'):
    try: shots.append((*exif(f), f))
    except Exception as ex: print('no leido', f, ex)
shots.sort()
groups = []
for s in shots:
    if groups and (s[0] - groups[-1][-1][0]).total_seconds() < 1.0: groups[-1].append(s)
    else: groups.append([s])
print('ARW en la tarjeta:', len(shots), '| rafagas de 5 o mas:', sum(len(g) >= 5 for g in groups))
for g in [g for g in groups if len(g) >= 5][-8:]:
    d = [(b[0] - a[0]).total_seconds() * 1000 for a, b in zip(g, g[1:])]
    span = (g[-1][0] - g[0][0]).total_seconds(); md = sorted(d)[len(d) // 2]
    head = sorted(d[:20]); print(f'{os.path.basename(g[0][-1])}..{os.path.basename(g[-1][-1])} {g[0][0]:%d %H:%M:%S} fotos={len(g)} dur={span:.3f}s fps_medio={(len(g)-1)/span:.2f} intervalo_mediano={md:.0f}ms min={min(d):.0f} max={max(d):.0f} | primeras 20: {(len(head))/sum(head)*1000:.2f} fps')
    s = g[0]; print(f'    compresion={s[2]} bits={s[3]} obturador={"1/%d" % round(1/s[4]) if s[4] and s[4] < 1 else s[4]} MB={s[5]/1e6:.1f} digitos_subseg={s[1]}')
    print('    intervalos ms:', [round(x) for x in d][:60])
