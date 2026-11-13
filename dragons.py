#!/usr/bin/env python3
import math
import os
import random
import shutil
import sys
import time

try:                                     # keyboard input (Unix)
    import select
    import termios
    import tty
    HAVE_TERMIOS = True
except ImportError:
    HAVE_TERMIOS = False
try:                                     # keyboard input (Windows)
    import msvcrt
except ImportError:
    msvcrt = None

ESC = "\x1b"
RESET = ESC + "[0m"
TAU = 2 * math.pi
INF = 1e9
FPS = 24
FRAME = 1.0 / FPS

#  terminal + grid helpers
def term_size():
    s = shutil.get_terminal_size((120, 36))
    return min(max(s.columns, 70), 240), min(max(s.lines - 1, 22), 70)


def draw(g):
    out = []
    for row in g:
        last = None
        parts = []
        for ch, fgc, bgc in row:
            key = (fgc, bgc)
            if key != last:
                s = RESET
                if fgc is not None:
                    s += f"{ESC}[38;5;{fgc}m"
                if bgc is not None:
                    s += f"{ESC}[48;5;{bgc}m"
                parts.append(s)
                last = key
            parts.append(ch)
        out.append("".join(parts))
    sys.stdout.write(ESC + "[H" + (RESET + "\n").join(out) + RESET)
    sys.stdout.flush()


def hide_cursor():
    sys.stdout.write(ESC + "[?25l" + ESC + "[2J")
    sys.stdout.flush()


def show_cursor():
    sys.stdout.write(RESET + ESC + "[?25h" + ESC + "[2J" + ESC + "[H")
    sys.stdout.flush()


class Keys:
    """Non-blocking single-key input; silently disabled if unavailable."""

    def __init__(self):
        self.ok = False
        self.win = False
        self.old = None
        try:
            if os.name == "nt" and msvcrt:
                self.ok = self.win = True
            elif HAVE_TERMIOS and sys.stdin.isatty():
                self.fd = sys.stdin.fileno()
                self.old = termios.tcgetattr(self.fd)
                tty.setcbreak(self.fd)
                self.ok = True
        except Exception:
            self.ok = False

    def read(self):
        keys = []
        if not self.ok:
            return keys
        try:
            if self.win:
                while msvcrt.kbhit():
                    keys.append(msvcrt.getwch())
            else:
                while select.select([self.fd], [], [], 0)[0]:
                    data = os.read(self.fd, 64)
                    if not data:
                        break
                    keys.extend(data.decode(errors="ignore"))
        except Exception:
            pass
        return keys

    def close(self):
        if self.old is not None:
            try:
                termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old)
            except Exception:
                pass

#tiny vector library (tuples)
def add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def mul(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def norm(a):
    l = math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2]) or 1e-9
    return (a[0] / l, a[1] / l, a[2] / l)


def lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t,
            a[2] + (b[2] - a[2]) * t)

#  palettes (8 shades, dark -> light) + a pale belly ramp
PALETTES = [
    dict(name="IGNIS",  body=[52, 88, 124, 160, 196, 202, 208, 215]),
    dict(name="VERDAN", body=[22, 28, 34, 40, 46, 82, 118, 157]),
    dict(name="AZURA",  body=[17, 18, 19, 25, 32, 38, 45, 123]),
    dict(name="AURUM",  body=[94, 130, 136, 172, 178, 214, 220, 229]),
    dict(name="NYX",    body=[53, 54, 90, 91, 127, 133, 171, 219]),
    dict(name="FROST",  body=[239, 242, 245, 248, 250, 252, 254, 231]),
]
for _p in PALETTES:
    _p["fire"] = _p["body"][2:] + [229, 231]
    _p["name_col"] = _p["body"][6]
BELLY = [94, 130, 136, 172, 178, 180, 223, 230]
SHADE_CH = ".:-=+*#%"
GLOW = [17, 53, 54, 90, 126, 162, 203, 209, 215, 221, 229, 231]

# formations: each maps (dragon index k, dragon count K, path time u)
# to a point in space.  The flock morphs by blending two of these.
def f_tornado(k, K, u):
    a = 1.0 * u + TAU * k / K
    r = 8.0 + 3.0 * math.sin(0.45 * u + 1.7 * k)
    y = 11.0 * math.sin(0.33 * u + 1.3 * k)
    return (r * math.cos(a), y, r * math.sin(a))


def f_trefoil(k, K, u):
    a = 0.5 * u + TAU * k / K
    c = 9.5 + 4.6 * math.cos(3 * a)
    return (c * math.cos(2 * a), 6.5 * math.sin(3 * a), c * math.sin(2 * a))


def f_hopf(k, K, u):
    R = 7.5
    grp, idx = k % 2, k // 2
    n = (K + 1) // 2 if grp == 0 else K // 2
    ph = TAU * idx / max(1, n)
    if grp == 0:                       # ring in the XZ plane
        a = 0.62 * u + ph
        return (R * math.cos(a) - R / 2, 1.8 * math.sin(2 * a), R * math.sin(a))
    b = -0.62 * u + ph + 1.3           # ring in the XY plane, counter-rotating
    return (R + R * math.cos(b) - R / 2, R * math.sin(b), 1.8 * math.sin(2 * b))


def f_sphere(k, K, u):
    psi = math.pi * (0.5 + 0.40 * math.sin(0.3 * u + 1.1 * k))
    phi = 1.15 * u + TAU * k / K
    R = 10.5 + 1.5 * math.sin(0.5 * u + k)
    return (R * math.sin(psi) * math.cos(phi), R * math.cos(psi),
            R * math.sin(psi) * math.sin(phi))


def f_helix(k, K, u):
    grp, side = k // 2, k % 2
    ng = (K + 1) // 2
    a = 1.2 * u + side * math.pi
    y = 7.0 * math.sin(0.27 * u) + (grp - (ng - 1) / 2) * 5.0
    return (5.5 * math.cos(a), y, 5.5 * math.sin(a))


FORMS = [f_tornado, f_trefoil, f_hopf, f_sphere, f_helix]
FORM_NAMES = ["TORNADO", "TREFOIL KNOT", "HOPF LINK", "SPHERE ORBIT", "TWIN HELIX"]
HOLD, MORPH = 15.0, 4.5
U_SPEED = 0.9
SPACING = 0.62

# one dragon
class Dragon:
    def __init__(self, k, K):
        self.k = k
        self.pal = PALETTES[k % len(PALETTES)]
        self.N = min(46, int(190 / K))
        n = self.N
        self.rad = []
        for i in range(n):
            x = i / (n - 1)
            r = 0.95 * (1 - x) ** 0.85 + 0.13
            if i < 6:
                r *= 0.62 + 0.076 * i          # slim neck behind the head
            self.rad.append(r)
        self.pts, self.fw, self.up, self.sd = [], [], [], []
        self.breath_until = 0.0
        self.next_breath = random.uniform(2.0, 6.0)

    def prepare(self):
        """Per-segment orthonormal frames from the sampled body points."""
        pts = self.pts
        n = len(pts)
        self.fw, self.up, self.sd = [], [], []
        for i in range(n):
            a = pts[max(i - 1, 0)]
            b = pts[min(i + 1, n - 1)]
            f = norm(sub(a, b))
            ref = (0.0, 1.0, 0.0) if abs(f[1]) < 0.93 else (1.0, 0.0, 0.0)
            s = norm(cross(f, ref))
            u = cross(s, f)
            self.fw.append(f)
            self.sd.append(s)
            self.up.append(u)


#the world / renderer
class Storm:
    def __init__(self, w, h, K=5):
        self.K = K
        self.time = 0.0
        self.f0, self.f1 = 0, 1
        self.morphing, self.m, self.s = False, 0.0, 0.0
        self.hold_t, self.held = 0.0, False
        self.cam_mode = 0
        self.cam_pos, self.cam_tgt = (0.0, 6.0, 40.0), (0.0, 0.0, 0.0)
        self.cam_yaw = 0.0
        self.flash = 0
        self.bolt = []
        self.parts = []
        self.dragons = [Dragon(k, K) for k in range(K)]
        self.resize(w, h)

    #setup 
    def resize(self, w, h):
        self.w, self.h = w, h
        self.f = h * 1.05
        self.cx, self.cy = w / 2.0, h / 2.0
        W3 = w * 3
        self.W3 = W3
        neb = []
        for y in range(h):
            row = []
            for x in range(W3):
                v = (math.sin(x * 0.045 + y * 0.09 + math.sin(y * 0.21) * 1.5)
                     + math.sin(x * 0.021 - y * 0.13 + 1.7)
                     + math.sin(math.hypot((x - W3 * 0.5) * 0.55, (y * 2 - h) * 0.8) * 0.07))
                row.append(54 if v > 1.8 else 53 if v > 1.25 else 17 if v > 0.6 else 16)
            neb.append(row)
        self.neb = neb
        self.stars = [(random.random(), random.random(), random.random() * 6.3,
                       random.choice("..+*")) for _ in range(max(30, w * h // 38))]
        self.dust = [[random.random() * TAU, random.uniform(-15, 15),
                      random.uniform(-1.5, 3.5), random.uniform(0.012, 0.05),
                      random.uniform(-0.01, 0.01)] for _ in range(max(80, w * h // 18))]

    def set_count(self, K):
        K = max(2, min(6, K))
        if K != self.K:
            self.K = K
            self.dragons = [Dragon(k, K) for k in range(K)]
            self.parts = []
            self.cam_mode = min(self.cam_mode, K)

    #formation control
    def start_morph(self, target):
        if not self.morphing:
            self.f1 = target % len(FORMS)
            self.m = 0.0
            self.morphing = True

    def path(self, k, u):
        a = FORMS[self.f0](k, self.K, u)
        if self.s > 0.0:
            b = FORMS[self.f1](k, self.K, u)
            return lerp(a, b, self.s)
        return a

    #simulation 
    def update(self, dt):
        self.time += dt
        if self.morphing:
            self.m += dt / MORPH
            if self.m >= 1.0:
                self.f0, self.morphing, self.m, self.hold_t = self.f1, False, 0.0, 0.0
            self.s = self.m * self.m * (3 - 2 * self.m) if self.morphing else 0.0
        else:
            self.s = 0.0
            if not self.held:
                self.hold_t += dt
                if self.hold_t > HOLD:
                    self.start_morph(self.f0 + 1)

        for d in self.dragons:
            self._sample_body(d)
            d.prepare()
            if self.time >= d.next_breath:
                d.breath_until = self.time + 1.4
                d.next_breath = self.time + random.uniform(5.0, 11.0)
            if self.time < d.breath_until:
                mouth = add(d.pts[0], mul(d.fw[0], 2.4))
                for _ in range(5):
                    v = add(mul(d.fw[0], random.uniform(0.55, 0.95)),
                            (random.uniform(-.07, .07), random.uniform(-.07, .07),
                             random.uniform(-.07, .07)))
                    if len(self.parts) < 1500:
                        life = random.randint(14, 24)
                        self.parts.append([mouth, v, life, life, d.pal])

        alive = []
        for q in self.parts:
            p, v = q[0], q[1]
            q[0] = (p[0] + v[0], p[1] + v[1], p[2] + v[2])
            q[1] = (v[0] * 0.985, v[1] * 0.985 + 0.004, v[2] * 0.985)
            q[2] -= 1
            if q[2] > 0:
                alive.append(q)
        self.parts = alive

        for dd in self.dust:
            dd[0] += dd[3]
            dd[1] += dd[4]
            if dd[1] > 15:
                dd[1] = -15
            elif dd[1] < -15:
                dd[1] = 15

        if self.flash > 0:
            self.flash -= 1
        elif random.random() < 0.006:
            self._new_bolt()

    def _sample_body(self, d):
        """Walk back along the flight path placing segments at equal spacing."""
        u = self.time * U_SPEED
        last = self.path(d.k, u)
        pts = [last]
        guard = 0
        while len(pts) < d.N and guard < 700:
            guard += 1
            u -= 0.04
            p = self.path(d.k, u)
            while len(pts) < d.N:
                vx, vy, vz = p[0] - last[0], p[1] - last[1], p[2] - last[2]
                dist = math.sqrt(vx * vx + vy * vy + vz * vz)
                if dist < SPACING:
                    break
                k = SPACING / dist
                last = (last[0] + vx * k, last[1] + vy * k, last[2] + vz * k)
                pts.append(last)
        d.pts = pts

    def _new_bolt(self):
        w, h = self.w, self.h
        x = random.randint(int(w * 0.15), int(w * 0.85))
        bolt = []
        yend = random.randint(int(h * 0.45), int(h * 0.85))
        for y in range(0, yend):
            dx = random.randint(-2, 2)
            x += dx
            ch = "|" if dx == 0 else ("/" if dx < 0 else "\\")
            bolt.append((x, y, ch))
            if random.random() < 0.07:                 # side branch
                bx = x
                for k in range(1, random.randint(3, 7)):
                    bx += random.choice((-2, 2))
                    bolt.append((bx, y + k, "/" if bx < x else "\\"))
        self.bolt = bolt
        self.flash = 4

    #camera
    def _camera(self, dt):
        t = self.time
        if self.cam_mode == 0:
            yaw = 0.16 * t + 0.5 * math.sin(0.05 * t)
            pitch = 0.28 + 0.22 * math.sin(0.07 * t)
            dist = 40 + 6 * math.sin(0.09 * t)
            self.cam_pos = (dist * math.cos(pitch) * math.sin(yaw), dist * math.sin(pitch),
                            dist * math.cos(pitch) * math.cos(yaw))
            self.cam_tgt = (0.0, 0.0, 0.0)
            self.cam_yaw = yaw
        else:
            d = self.dragons[(self.cam_mode - 1) % len(self.dragons)]
            head, fw = d.pts[0], norm(sub(d.pts[0], d.pts[min(4, len(d.pts) - 1)]))
            want_pos = add(sub(head, mul(fw, 10.0)), (0.0, 5.0, 0.0))
            want_tgt = add(head, mul(fw, 9.0))
            a = 1 - math.exp(-dt * 5.0)
            b = 1 - math.exp(-dt * 8.0)
            self.cam_pos = lerp(self.cam_pos, want_pos, a)
            self.cam_tgt = lerp(self.cam_tgt, want_tgt, b)
            self.cam_yaw = math.atan2(fw[0], fw[2])
        C, T = self.cam_pos, self.cam_tgt
        F = norm(sub(T, C))
        ref = (0.0, 1.0, 0.0) if abs(F[1]) < 0.98 else (1.0, 0.0, 0.0)
        Rt = norm(cross(F, ref))
        Ut = cross(Rt, F)
        self.C, self.Rt, self.Ut, self.Ft = C, Rt, Ut, F
        self.zmid = math.sqrt(dot(sub(T, C), sub(T, C)))
        o = sub((0.0, 0.0, 0.0), C)                       # storm heart in camera space
        self.orb_c = (dot(o, Rt), dot(o, Ut), dot(o, F))
        L = norm((0.4, 0.85, 0.35))                       # "moon" light
        self.ld_c = (dot(L, Rt), dot(L, Ut), dot(L, F))
        self.Lw = L
        self.wup_c = (Rt[1], Ut[1], F[1])                  # world up in camera space

    def proj(self, p):
        C, Rt, Ut, Ft = self.C, self.Rt, self.Ut, self.Ft
        vx, vy, vz = p[0] - C[0], p[1] - C[1], p[2] - C[2]
        zc = vx * Ft[0] + vy * Ft[1] + vz * Ft[2]
        if zc < 1.5:
            return None
        xc = vx * Rt[0] + vy * Rt[1] + vz * Rt[2]
        yc = vx * Ut[0] + vy * Ut[1] + vz * Ut[2]
        inv = self.f / zc
        return (self.cx + 2 * xc * inv, self.cy - yc * inv, zc)

    #rendering primitives
    def _fog(self, zc):
        v = 1.05 - (zc - (self.zmid - 12)) / 34.0
        return 0.4 if v < 0.4 else (1.05 if v > 1.05 else v)

    def sphere(self, p, R, ramp, parity=0):
        C, Rt, Ut, Ft = self.C, self.Rt, self.Ut, self.Ft
        vx, vy, vz = p[0] - C[0], p[1] - C[1], p[2] - C[2]
        zc = vx * Ft[0] + vy * Ft[1] + vz * Ft[2]
        if zc < 1.5:
            return
        xc = vx * Rt[0] + vy * Rt[1] + vz * Rt[2]
        yc = vx * Ut[0] + vy * Ut[1] + vz * Ut[2]
        inv = self.f / zc
        rsy = R * inv
        rsx = 2 * rsy
        scx = self.cx + 2 * xc * inv
        scy = self.cy - yc * inv
        w, h = self.w, self.h
        if scx + rsx < 0 or scx - rsx >= w or scy + rsy < 0 or scy - rsy >= h:
            return

        ox, oy, oz = self.orb_c
        lx, ly, lz = ox - xc, oy - yc, oz - zc
        ld = math.sqrt(lx * lx + ly * ly + lz * lz) + 1e-6
        att = 1.0 / (1.0 + (ld / 16.0) ** 2)
        lx, ly, lz = lx / ld, ly / ld, lz / ld
        Lx, Ly, Lz = self.ld_c
        wx, wy, wz = self.wup_c
        fog = self._fog(zc)
        g, zb = self.g, self.zb
        sqrt = math.sqrt

        if rsy < 0.65:                                   # far away: single cell
            sx, sy = int(round(scx)), int(round(scy))
            if 0 <= sx < w and 0 <= sy < h and zc < zb[sy][sx]:
                zb[sy][sx] = zc
                I = (0.14 + 0.78 * att * max(0.0, -lz) + 0.32 * max(0.0, -Lz)) * fog
                idx = max(0, min(7, int(I * 8)))
                c = g[sy][sx]
                c[0], c[1], c[2] = SHADE_CH[idx], ramp[min(7, idx + 1)], ramp[max(0, idx - 1)]
            return

        y0 = max(0, int(math.floor(scy - rsy)))
        y1 = min(h - 1, int(math.ceil(scy + rsy)))
        for sy in range(y0, y1 + 1):
            dy = (sy - scy) / rsy
            dy2 = dy * dy
            if dy2 > 1.0:
                continue
            half = rsx * sqrt(1.0 - dy2)
            xa = max(0, int(math.ceil(scx - half)))
            xb = min(w - 1, int(math.floor(scx + half)))
            row, zrow = g[sy], zb[sy]
            for sx in range(xa, xb + 1):
                dx = (sx - scx) / rsx
                nz2 = 1.0 - dx * dx - dy2
                if nz2 < 0.0:
                    continue
                nz = sqrt(nz2)
                z = zc - nz * R
                if z >= zrow[sx]:
                    continue
                zrow[sx] = z
                d_orb = dx * lx - dy * ly - nz * lz
                d_dir = dx * Lx - dy * Ly - nz * Lz
                rim = (1.0 - nz)
                I = 0.14 + 0.38 * rim * rim
                if d_orb > 0:
                    I += 0.78 * att * d_orb
                if d_dir > 0:
                    I += 0.32 * d_dir
                idx = int(I * fog * 8)
                if idx > 7:
                    idx = 7
                elif idx < 0:
                    idx = 0
                belly = dx * wx - dy * wy - nz * wz < -0.5
                rmp = BELLY if belly else ramp
                c = row[sx]
                c[0] = SHADE_CH[idx]
                c[1] = rmp[idx + 1 if idx < 7 else 7]
                bi = idx - 1 - parity
                c[2] = rmp[bi if bi > 0 else 0]

    def line3(self, a, b, fg, ch=None, bias=0.3):
        pa, pb = self.proj(a), self.proj(b)
        if pa is None or pb is None:
            return
        x0, y0, z0 = pa
        x1, y1, z1 = pb
        dx, dy = x1 - x0, y1 - y0
        if ch is None:
            vy = 2 * dy
            if abs(vy) < 0.4 * abs(dx):
                ch = "-"
            elif abs(vy) > 2.5 * abs(dx):
                ch = "|"
            else:
                ch = "/" if dx * dy < 0 else "\\"
        n = int(max(abs(dx), abs(dy) * 2)) + 1
        n = min(n, 400)
        g, zb, w, h = self.g, self.zb, self.w, self.h
        for i in range(n + 1):
            t = i / n
            x = int(round(x0 + dx * t))
            y = int(round(y0 + dy * t))
            if 0 <= x < w and 0 <= y < h and z0 + (z1 - z0) * t - bias < zb[y][x]:
                c = g[y][x]
                c[0], c[1] = ch, fg

    def tri(self, A, B, C3, fg, bg_a, bg_b):
        """Scanline triangle with z-interpolation (screen-space vertices)."""
        (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = sorted((A, B, C3), key=lambda p: p[1])
        if y2 - y0 < 1e-6:
            return
        w, h, g, zb = self.w, self.h, self.g, self.zb
        ya = max(0, int(math.ceil(y0)))
        yb = min(h - 1, int(math.floor(y2)))
        for y in range(ya, yb + 1):
            t = (y - y0) / (y2 - y0)
            xl, zl = x0 + (x2 - x0) * t, z0 + (z2 - z0) * t
            if y < y1:
                if y1 - y0 > 1e-6:
                    s = (y - y0) / (y1 - y0)
                    xr, zr = x0 + (x1 - x0) * s, z0 + (z1 - z0) * s
                else:
                    xr, zr = x1, z1
            else:
                if y2 - y1 > 1e-6:
                    s = (y - y1) / (y2 - y1)
                    xr, zr = x1 + (x2 - x1) * s, z1 + (z2 - z1) * s
                else:
                    xr, zr = x1, z1
            if xl > xr:
                xl, xr, zl, zr = xr, xl, zr, zl
            xa = max(0, int(math.ceil(xl)))
            xb = min(w - 1, int(math.floor(xr)))
            span = xr - xl
            row, zrow = g[y], zb[y]
            for x in range(xa, xb + 1):
                z = zl + (zr - zl) * ((x - xl) / span) if span > 1e-6 else zl
                if z < zrow[x]:
                    zrow[x] = z
                    c = row[x]
                    if (x + y) & 1:
                        c[0], c[2] = ":", bg_a
                    else:
                        c[0], c[2] = ".", bg_b
                    c[1] = fg

    #dragon parts
    def draw_dragon(self, d, t):
        pal = d.pal
        n = len(d.pts)
        for i in range(n - 1, 0, -1):
            self.sphere(d.pts[i], d.rad[i], pal["body"], i & 1)
        #dorsal spines
        top = pal["body"][7]
        for i in range(2, int(n * 0.82), 2):
            root = add(d.pts[i], mul(d.up[i], d.rad[i] * 0.95))
            tip = add(add(root, mul(d.up[i], 0.45 + 0.5 * d.rad[i])), mul(d.fw[i], -0.35))
            self.line3(root, tip, top, bias=0.4)
        self.draw_wings(d, t)
        self.draw_head(d, t)

    def draw_head(self, d, t):
        pal = d.pal["body"]
        p0, f, u, s = d.pts[0], d.fw[0], d.up[0], d.sd[0]
        breathing = self.time < d.breath_until
        opn = 0.95 if breathing else 0.15 + 0.1 * math.sin(3 * t + d.k)

        def at(a, b, c):
            return add(add(add(p0, mul(f, a)), mul(u, b)), mul(s, c))
        self.sphere(at(0.2, 0, 0), 1.0, pal, 0)                         # skull
        self.sphere(at(1.45, 0.05, 0), 0.62, pal, 1)                    # snout
        self.sphere(at(2.15, 0.0, 0), 0.42, pal, 0)                     # nose
        self.sphere(at(1.5, -0.55 - 0.5 * opn, 0), 0.40, pal, 1)        # lower jaw
        self.sphere(at(2.0, -0.5 - 0.75 * opn, 0), 0.30, pal, 0)        # chin
        for sg in (-1, 1):                                              # horns
            base = at(-0.1, 0.75, 0.55 * sg)
            mid = at(-1.0, 1.25, 1.05 * sg)
            tip = at(-1.9, 1.35, 1.40 * sg)
            self.line3(base, mid, 230, bias=0.6)
            self.line3(mid, tip, 230, bias=0.6)
            e = self.proj(at(0.85, 0.42, 0.62 * sg))                    # eyes
            if e:
                x, y = int(round(e[0])), int(round(e[1]))
                if 0 <= x < self.w and 0 <= y < self.h and e[2] - 0.9 < self.zb[y][x]:
                    c = self.g[y][x]
                    c[0], c[1], c[2] = "O", (196 if breathing else 226), 16

    def draw_wings(self, d, t):
        n = len(d.pts)
        iw = 6
        if n < 14:
            return
        pal = d.pal["body"]
        f, u, s = d.fw[iw], d.up[iw], d.sd[iw]
        k = d.k
        fl = 0.50 * math.sin(TAU * 0.85 * t + k * 1.3) + 0.25
        flt = 0.50 * math.sin(TAU * 0.85 * t + k * 1.3 - 0.9) + 0.05
        anchor = d.pts[min(n - 1, iw + 6)]
        Tpt = add(anchor, mul(d.up[min(n - 1, iw + 6)], 0.15))
        R = add(d.pts[iw], mul(u, d.rad[iw] * 0.8))
        scale = 1.0 if self.K <= 4 else 0.9
        for sg in (-1, 1):
            side = mul(s, sg)
            d_el = norm(add(mul(side, math.cos(fl)), mul(u, math.sin(fl))))
            E = sub(add(R, mul(d_el, 3.0 * scale)), mul(f, 0.3))
            tips = []
            for bk, ln in ((0.25, 5.6), (0.8, 5.4), (1.4, 4.2)):
                dj = norm(sub(add(mul(side, math.cos(flt)), mul(u, math.sin(flt))), mul(f, bk)))
                tips.append(add(E, mul(dj, ln * scale)))
            m01 = add(E, mul(sub(lerp(tips[0], tips[1], 0.5), E), 0.78))
            m12 = add(E, mul(sub(lerp(tips[1], tips[2], 0.5), E), 0.78))
            poly = [R, E, tips[0], m01, tips[1], m12, tips[2], Tpt]
            pr = [self.proj(v) for v in poly]
            if any(p is None for p in pr):
                continue
            # membrane shading from the face normal
            nrm = norm(cross(sub(E, R), sub(tips[1], R)))
            cen = lerp(R, tips[1], 0.5)
            lo = norm(sub((0.0, 0.0, 0.0), cen))
            dist = math.sqrt(dot(cen, cen))
            att = 1.0 / (1.0 + (dist / 16.0) ** 2)
            zc = pr[2][2]
            I = (0.22 + 0.55 * att * abs(dot(nrm, lo)) + 0.28 * abs(dot(nrm, self.Lw))) * self._fog(zc)
            idx = max(1, min(6, int(I * 8)))
            fg = pal[min(7, idx + 2)]
            bga, bgb = pal[max(0, idx - 2)], pal[max(0, idx - 3)]
            for i in range(1, 7):
                self.tri(pr[0], pr[i], pr[i + 1], fg, bga, bgb)
            for a, b in ((R, E), (E, tips[0]), (E, tips[1]), (E, tips[2])):
                self.line3(a, b, 230, bias=0.6)

    #frame 
    def render(self, dt=1 / 24):
        w, h = self.w, self.h
        self._camera(dt)
        t = self.time
        off = int(self.cam_yaw * w * 0.5) % self.W3
        W3 = self.W3
        self.g = [[[" ", None, self.neb[y][(x + off) % W3]] for x in range(w)]
                  for y in range(h)]
        self.zb = [[INF] * w for _ in range(h)]
        g = self.g

        # starfield with parallax + twinkle
        so = self.cam_yaw * w * 0.8
        for sx, sy, ph, ch in self.stars:
            if math.sin(t * 1.9 + ph) > -0.35:
                x, y = int((sx * w + so) % w), int(sy * h)
                c = g[y][x]
                c[0], c[1] = ch, (231 if math.sin(t * 1.9 + ph) > 0.6 else 248)

        #lightning( dont need)
        if self.flash > 0 and self.flash % 2 == 0 or self.flash == 3:
            for x, y, ch in self.bolt:
                if 0 <= x < w and 0 <= y < h:
                    c = g[y][x]
                    c[0], c[1], c[2] = ch, 231, 61
                    if x + 1 < w:
                        g[y][x + 1][2] = 60

        # dragons: draw everything, z-buffer sorts it out
        for d in self.dragons:
            self.draw_dragon(d, t)

        # breath particles
        for p, v, life, mx, pal in self.parts:
            pr = self.proj(p)
            if not pr:
                continue
            x, y = int(round(pr[0])), int(round(pr[1]))
            if 0 <= x < w and 0 <= y < h and pr[2] - 0.5 < self.zb[y][x]:
                r = life / mx
                c = g[y][x]
                c[0] = ".:*#@"[min(4, int(r * 5))]
                c[1] = pal["fire"][min(7, int(r * 8))]
                if r > 0.45:
                    c[2] = pal["body"][1]

        # swirling dust funnel
        for a, y, rr, _sp, _vy in self.dust:
            r = 3.5 + 0.8 * abs(y) + rr
            pr = self.proj((r * math.cos(a), y, r * math.sin(a)))
            if not pr:
                continue
            x, yy = int(round(pr[0])), int(round(pr[1]))
            if 0 <= x < w and 0 <= yy < h and pr[2] < self.zb[yy][x]:
                near = (self.zmid - pr[2]) / 14.0
                c = g[yy][x]
                if c[0] == " ":
                    c[0] = "." if near < 0.3 else ","
                    c[1] = 60 if near < -0.2 else (103 if near < 0.3 else 146)

        self.draw_orb(t)
        self.draw_hud()
        return g

    def draw_orb(self, t):
        xc, yc, zc = self.orb_c
        if zc < 2.5:
            return
        w, h, g, zb = self.w, self.h, self.g, self.zb
        inv = self.f / zc
        scx, scy = self.cx + 2 * xc * inv, self.cy - yc * inv
        pulse = 0.92 + 0.08 * math.sin(t * 3.1)
        Rg, Rc = 6.5 * inv * pulse, 1.0 * inv * pulse
        if Rg < 0.5:
            return
        for sy in range(max(0, int(scy - Rg)), min(h - 1, int(scy + Rg)) + 1):
            dy = (sy - scy) / Rg
            for sx in range(max(0, int(scx - 2 * Rg)), min(w - 1, int(scx + 2 * Rg)) + 1):
                dx = (sx - scx) / (2 * Rg)
                d2 = dx * dx + dy * dy
                if d2 >= 1.0 or zb[sy][sx] < zc:
                    continue
                i = (1.0 - math.sqrt(d2)) ** 2 * pulse
                gi = int(i * (len(GLOW) - 1))
                if gi <= 0:
                    continue
                c = g[sy][sx]
                c[2] = GLOW[gi]
                if (sx - scx) ** 2 / 4 + (sy - scy) ** 2 <= Rc * Rc:
                    c[0], c[1], c[2] = " ", None, 231
        # lens flare cross
        for k in range(2, int(Rg * 3)):
            fade = 1.0 - k / (Rg * 3)
            col = 231 if fade > 0.7 else (222 if fade > 0.4 else 139)
            for sx in (int(scx + k * 2), int(scx - k * 2)):
                if 0 <= sx < w and 0 <= int(scy) < h and zb[int(scy)][sx] > zc and g[int(scy)][sx][0] == " ":
                    g[int(scy)][sx][0], g[int(scy)][sx][1] = "-", col
            for sy in (int(scy + k * 0.8), int(scy - k * 0.8)):
                if 0 <= sy < h and 0 <= int(scx) < w and zb[sy][int(scx)] > zc and g[sy][int(scx)][0] == " ":
                    g[sy][int(scx)][0], g[sy][int(scx)][1] = "|", col

    def draw_hud(self):
        g, w, h = self.g, self.w, self.h

        def text(x, y, s, fg, bg=None):
            for i, ch in enumerate(s):
                if 0 <= x + i < w and 0 <= y < h:
                    c = g[y][x + i]
                    c[0], c[1] = ch, fg
                    if bg is not None:
                        c[2] = bg
        text(1, 0, " DRAGONSTORM ", 16, 220)
        name = FORM_NAMES[self.f0]
        if self.morphing:
            bar = "#" * int(self.m * 10) + "-" * (10 - int(self.m * 10))
            label = f" {name} -> {FORM_NAMES[self.f1]} [{bar}] "
        else:
            label = f" FORMATION: {name}{' (held)' if self.held else ''} "
        text(15, 0, label, 51, 16)
        cam = "ORBIT" if self.cam_mode == 0 else \
            "CHASE " + self.dragons[(self.cam_mode - 1) % len(self.dragons)].pal["name"]
        text(w - len(cam) - 9, 0, f" CAM: {cam} ", 213, 16)
        x = 1
        for d in self.dragons:
            nm = f" {d.pal['name']} "
            text(x, h - 1, nm, d.pal["name_col"], 16)
            x += len(nm) + 1
        hint = " n/p form  h hold  c cam  f fire  +/- dragons  q quit "
        text(w - len(hint) - 1, h - 1, hint, 245, 16)

    def breathe_all(self):
        for d in self.dragons:
            d.breath_until = self.time + 2.0

#main loop
def main():
    K = 5
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        K = max(2, min(6, int(sys.argv[1])))
    os.system("")                    
    keys = Keys()
    hide_cursor()
    try:
        w, h = term_size()
        storm = Storm(w, h, K)
        last = time.perf_counter()
        while True:
            now = time.perf_counter()
            dt = min(0.1, now - last)
            last = now
            for k in keys.read():
                k = k.lower()
                if k == "q":
                    return
                elif k in ("n", " "):
                    storm.start_morph(storm.f0 + 1)
                elif k == "p":
                    storm.start_morph(storm.f0 - 1)
                elif k == "h":
                    storm.held = not storm.held
                elif k == "c":
                    storm.cam_mode = (storm.cam_mode + 1) % (storm.K + 1)
                elif k == "f":
                    storm.breathe_all()
                elif k in ("+", "="):
                    storm.set_count(storm.K + 1)
                elif k in ("-", "_"):
                    storm.set_count(storm.K - 1)
            nw, nh = term_size()
            if (nw, nh) != (storm.w, storm.h):
                storm.resize(nw, nh)
                sys.stdout.write(ESC + "[2J")
            storm.update(dt)
            draw(storm.render(dt))
            time.sleep(max(0.0, FRAME - (time.perf_counter() - now)))
    except KeyboardInterrupt:
        pass
    finally:
        keys.close()
        show_cursor()


if __name__ == "__main__":
    main()
