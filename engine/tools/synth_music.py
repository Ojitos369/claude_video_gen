# Instrumental bed synthesised locally (numpy/scipy): fallback when a music service is unavailable.
#   python engine/tools/synth_music.py <project> --seconds 39 --bpm 120 --out audio/music.wav [--seed 1]
# Cute/mysterious pop loop: plucked arpeggio, glockenspiel hook, bass, pad, kick/clap/hats. Structure (fractions of the piece):
# hook (full energy at 0 s) -> groove -> tender breakdown without drums (--breakdown, default 55%-62%) -> 1-bar riser -> groove -> final hit + ring-out.
# Key A minor, progression Am-F-C-G, one chord per bar. Mono 44.1 kHz WAV.
import argparse, os, sys
import numpy as np
from scipy.signal import butter, lfilter
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import soundfile as sf
SR = 44100
hz = lambda m: 440.0 * 2 ** ((m - 69) / 12)
def lp(x, f, o=2): return lfilter(*butter(o, f / (SR / 2), "low"), x)
def hp(x, f, o=2): return lfilter(*butter(o, f / (SR / 2), "high"), x)
def t_(d): return np.arange(int(d * SR)) / SR
def pluck(m, d=0.35):
    t = t_(d); f = hz(m); x = sum(np.sin(2 * np.pi * f * k * t + k) / k for k in (1, 2, 3, 4)) * np.exp(-t * 9)
    return lp(x, 3500) * 0.5
def bell(m, d=1.2):
    t = t_(d); f = hz(m)
    return sum(a * np.sin(2 * np.pi * f * r * t) * np.exp(-t * dc) for r, a, dc in ((1, 1, 3.5), (2.76, .5, 6), (5.4, .25, 9), (8.93, .12, 12))) * 0.35
def bass(m, d=0.45):
    t = t_(d); f = hz(m); x = np.sin(2 * np.pi * f * t) + 0.35 * np.sign(np.sin(2 * np.pi * f * t))
    return lp(x, 400) * np.minimum(1, t * 200) * np.exp(-t * 4) * 0.9
def kick():
    t = t_(0.3); ph = 2 * np.pi * np.cumsum(45 + 110 * np.exp(-t * 30)) / SR
    return np.sin(ph) * np.exp(-t * 11) * 1.1
def clap(rng):
    x = np.zeros(int(.25 * SR))
    for o in (0, .012, .024): n = rng.standard_normal(int(.2 * SR)); i = int(o * SR); x[i:i + len(n)] += hp(lp(n, 6000), 1000) * np.exp(-t_(.2) * (40 if o < .024 else 18))
    return x * 0.45
def hat(rng, op=False):
    d = .18 if op else .05; return hp(rng.standard_normal(int(d * SR)), 7000) * np.exp(-t_(d) * (18 if op else 70)) * 0.22
def pad(ms, d):
    t = t_(d); x = 0
    for m in ms:
        for dt in (-0.12, 0, 0.12): x = x + np.sign(np.sin(2 * np.pi * hz(m + dt) * t)) * 0.1
    return lp(x, 1400) * np.minimum(1, t * 3) * np.minimum(1, (d - t) * 4)

ap = argparse.ArgumentParser(); ap.add_argument("project"); ap.add_argument("--seconds", type=float, default=39)
ap.add_argument("--bpm", type=float, default=120); ap.add_argument("--breakdown", type=float, nargs=2, help="start end (s) of the drumless tender part; default 55%%-62%%"); ap.add_argument("--out", default="audio/music.wav"); ap.add_argument("--seed", type=int, default=1)
a = ap.parse_args()
from engine.common import Project
pr = Project(a.project)
rng = np.random.default_rng(a.seed); beat = 60 / a.bpm; bar = 4 * beat; total = a.seconds
out = np.zeros(int((total + 2) * SR)); side = np.ones_like(out)
def put(x, t, g=1.0, buf=None):
    buf = out if buf is None else buf; i = int(t * SR)
    if 0 <= i < len(buf): e = min(len(buf), i + len(x)); buf[i:e] += x[:e - i] * g
CH = [(57, (45, 57, 60, 64)), (53, (41, 53, 57, 60)), (48, (36, 48, 52, 55)), (55, (43, 55, 59, 62))]   # (root, bass+triad) Am F C G
HOOK = {0: [(0, 76), (1.5, 79), (2, 81), (3, 79)], 1: [(0, 77), (1.5, 81), (2, 84), (3, 81)], 2: [(0, 76), (1.5, 79), (2, 84), (3, 83)], 3: [(0, 79), (1.5, 83), (2, 86), (3, 83)]}
BA, BB = a.breakdown or (0.55 * total, 0.62 * total)
end_hit = total - 1.0; nb = int(end_hit / bar) + 1
def drums_on(t): return not (BA <= t < BB) and t < end_hit + 0.01
def riser_zone(t): return BB - bar <= t < BB
for b in range(nb):
    t0 = b * bar; c = CH[b % 4]; tones = c[1][1:]
    if t0 > end_hit: break
    put(pad(tones, bar * 1.02), t0, 0.7 if not (BA <= t0 < BB) else 1.1)
    for s in range(8):                                     # plucked arpeggio, 8ths
        t = t0 + s * beat / 2
        if t < end_hit: put(pluck(tones[[0, 1, 2, 1, 0, 1, 2, 3][s] % len(tones)] + 12), t, 0.55 if s % 2 else 0.8)
    for o, m in HOOK[b % 4]:
        t = t0 + o * beat
        if t < end_hit and (b >= 1 or o >= 2): put(bell(m), t, 0.8)
    for s in range(4):                                     # bass
        t = t0 + s * beat
        if drums_on(t) and t < end_hit: put(bass(c[0] - 12 + (12 if s == 3 else 0)), t + (0.0 if s % 2 == 0 else beat / 2 * 0), 0.9)
    for s in range(8):
        t = t0 + s * beat / 2
        if not drums_on(t): continue
        if s % 4 == 0 or (s == 6 and b % 2): put(kick(), t, 0.95); put(kick(), t, 1, side)   # kick (side only used as pump envelope)
        if s in (2, 6): put(clap(rng), t, 0.9)
        put(hat(rng, op=(s % 2 == 1 and b % 2 == 1)), t, 1 if s % 2 == 0 else 0.6)
        if t > 0.8 * total and s % 2 == 1: put(hat(rng), t + beat / 4, 0.5)
    if BA <= t0 < BB:                  # tender breakdown: extra soft bells
        for s in range(4): put(bell(CH[b % 4][1][3 - s % 3] + 24, 1.5), t0 + s * beat, 0.45)
# pump on the pad from kicks: simple ducking envelope
pump = np.ones_like(out)
for b in range(nb):
    for s in range(4):
        t = b * bar + s * beat
        if drums_on(t):
            i = int(t * SR); n = int(0.18 * SR); e = min(len(pump), i + n)
            if e > i: pump[i:e] = np.minimum(pump[i:e], 0.55 + 0.45 * np.linspace(0, 1, n)[:e - i] ** 2)
out *= 0.75 + 0.25 * pump
# riser before the return of the drums + downsweep
rz = int(bar * SR); r0 = int((BB - bar) * SR)
if r0 >= 0:
    n = rng.standard_normal(rz); env = np.linspace(0, 1, rz) ** 2.2
    out[r0:r0 + rz] += hp(n, 2500) * env * 0.35 + np.sin(2 * np.pi * np.cumsum(300 + 1500 * env) / SR) * env * 0.12
# final hit on the last downbeat-ish + ring-out
th = end_hit; put(kick(), th, 1.2); put(clap(rng), th, 1.0)
for m in (57, 64, 69, 72, 76): put(bell(m, 2.0), th, 0.6)
put(pad((45, 57, 60, 64), 1.3), th, 0.9)
N = int(total * SR); out = out[:N]
fade = int(0.35 * SR); out[-fade:] *= np.linspace(1, 0, fade)
out = out / np.percentile(np.abs(out), 99.7) * 0.7; out = np.tanh(out * 1.2) / np.tanh(1.2); out = out / np.abs(out).max() * 0.85
os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
path = a.out if os.path.isabs(a.out) else pr.p(a.out)
sf.write(path, out.astype(np.float32), SR); print("música sintetizada:", path, round(total, 1), "s", a.bpm, "bpm")
