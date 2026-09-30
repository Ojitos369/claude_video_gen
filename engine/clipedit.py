# Clip editor: sequence of videos (sped up, muted) and images over a blurred copy of themselves, with TikTok-style effects
# (hook flash/burst, beat-synced zoom punches, shake + chromatic split on cuts, sparkles, emoji stickers, progress bar, vignette),
# centred word-by-word captions and a mix of narration + ducked music + synthesised SFX.
#   python engine/clipedit.py <project> --frame 0.3 12.5 ...   -> render/frame_<t>.png (stills for checks)
#   python engine/clipedit.py <project> --preview 4 9          -> out/preview.mp4 (A..B seconds, with audio)
#   python engine/clipedit.py <project> [--force]              -> out/<output> (renders everything; --force rebuilds the clip cache)
#   python engine/clipedit.py <project> --audio                -> only audio/mix.wav
# Inputs in the project folder: config.json (aspect/fps), edit.json, captions.json (chunks with per-word times), audio/voice.wav,
# audio/music.wav (see edit.json keys below). Cache: render/clip_<n>.mp4 (videos already speed-changed, blurred background, 1080x1920).
# edit.json: {fps, bpm, clips:[{src, dur, kind: video|image, zoom:[z0,z1], pan:[x,y]}], hits:[t..] (zoom snap + flash),
#   stickers:[{t, e: emoji, x, y (0..1), size, kind: pop|rise, n, hold}], sfx:[{t, k: impact|pop|chirp|sparkle|ding|tick}],
#   breakdown:[a,b] (no punch zoom), bursts:[t..] (radial rays), music_db, voice_db, duck_db, caption_y (0..1, default 0.5), caption_scale (default 1),
#   fade_out (s, default 0.25); sfx kinds: impact|pop|chirp|sparkle|ding|tick|whoosh|growl|squeak}
import argparse, json, math, os, subprocess, sys
import numpy as np, soundfile as sf
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageEnhance, ImageOps
from scipy.signal import butter, lfilter, resample_poly
from common import project_from_argv, video_encoder_args

PR = project_from_argv()
CFG, P = PR.cfg, PR.p
W, H = CFG["width"], CFG["height"]
FPS = float(CFG["fps"])
S = min(W, H) / 1080
ap = argparse.ArgumentParser()
ap.add_argument("--frame", type=float, nargs="+"); ap.add_argument("--preview", type=float, nargs=2)
ap.add_argument("--audio", action="store_true"); ap.add_argument("--force", action="store_true")
A = ap.parse_args()
E = json.load(open(P("edit.json")))
CAPS = json.load(open(P("captions.json")))
CL = E["clips"]
starts = np.cumsum([0] + [c["dur"] for c in CL]); TOTAL = float(starts[-1]); NF = int(round(TOTAL * FPS))
BEAT = 60 / E.get("bpm", 120)
BRK = E.get("breakdown", [1e9, 1e9])
HITS, BURSTS = E.get("hits", []), E.get("bursts", [0.0])
ease_out = lambda u: 1 - (1 - min(max(u, 0), 1)) ** 3
ease_io = lambda u: (lambda v: v * v * (3 - 2 * v))(min(max(u, 0), 1))
def back(u, k=2.2): u = min(max(u, 0), 1) - 1; return 1 + (k + 1) * u ** 3 + k * u ** 2
def lerp(a, b, u): return a + (b - a) * u
def sh(*a): subprocess.run(a, check=True)

# ---------------------------------------------------------------- clip cache (videos)
def prep_video(i, c):
    out = PR.rdir(f"clip_{i}.mp4")
    if os.path.exists(out) and not A.force: return out
    src = P(c["src"])
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=duration", "-of", "csv=p=0", src],
                               capture_output=True, text=True, check=True).stdout.split()[0])
    sp = dur / c["dur"]; n = int(round(c["dur"] * FPS))
    vf = (f"setpts=PTS/{sp:.5f},fps={FPS},split[a][b];[a]scale={W // 4}:{H // 4}:force_original_aspect_ratio=increase,crop={W // 4}:{H // 4},gblur=sigma=5,"
          f"scale={W}:{H}:flags=bicubic,eq=brightness=-0.12:saturation=1.3[bg];[b]scale={W}:{H}:force_original_aspect_ratio=decrease:flags=lanczos[fg];"
          "[bg][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p")
    print(f"clip {i}: {c['src']} x{sp:.1f} -> {c['dur']} s", flush=True)
    sh("ffmpeg", "-y", "-loglevel", "error", "-i", src, "-an", "-vf", vf, "-frames:v", str(n), "-c:v", "libx264", "-crf", "12", "-preset", "veryfast", "-g", "8", out)
    return out

class Reader:
    """Sequential RGB frames of a cached clip; reopens if the requested frame is not the next one."""
    def __init__(s, path): s.path, s.p, s.nxt = path, None, -1
    def get(s, idx):
        if idx != s.nxt:
            s.close()
            s.p = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-ss", f"{idx / FPS:.4f}", "-i", s.path, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                                   stdout=subprocess.PIPE); s.nxt = idx
        b = s.p.stdout.read(W * H * 3)
        if len(b) < W * H * 3: s.nxt = -1; return s.last
        s.nxt += 1; s.last = np.frombuffer(b, np.uint8).reshape(H, W, 3); return s.last
    def close(s):
        if s.p: s.p.stdout.close(); s.p.kill(); s.p.wait(); s.p = None

# ---------------------------------------------------------------- images: blurred cover background + rounded foreground, base at ZM x output size
ZM = 1.6
def prep_image(c):
    im = Image.open(P(c["src"])).convert("RGB"); BW, BH = int(W * ZM), int(H * ZM)
    bg = ImageOps.fit(im, (BW // 8, BH // 8), Image.LANCZOS).filter(ImageFilter.GaussianBlur(5)).resize((BW, BH), Image.BICUBIC)
    bg = ImageEnhance.Color(ImageEnhance.Brightness(bg).enhance(0.8)).enhance(1.3)
    k = min(BW * 0.97 / im.width, BH * 0.97 / im.height); fw, fh = int(im.width * k), int(im.height * k)
    fg = im.resize((fw, fh), Image.LANCZOS)
    m = Image.new("L", (fw, fh), 0); ImageDraw.Draw(m).rounded_rectangle((0, 0, fw - 1, fh - 1), int(46 * ZM * S), fill=255)
    sd = Image.new("L", (BW, BH), 0); sd.paste(m.point(lambda v: v * 0.7), ((BW - fw) // 2, (BH - fh) // 2 + int(14 * ZM)))
    bg.paste((0, 0, 0), mask=sd.filter(ImageFilter.GaussianBlur(28 * ZM)))
    bg.paste(fg, ((BW - fw) // 2, (BH - fh) // 2), m)
    return bg

def view(img, z, cx, cy, zmb):
    """Crop of a base image (size = output * zmb) at zoom z centred on (cx, cy) in 0..1 coordinates, resized to the output."""
    bw, bh = img.size; w, h = bw / z, bh / z
    x0 = min(max(cx * bw - w / 2, 0), bw - w); y0 = min(max(cy * bh - h / 2, 0), bh - h)
    return np.asarray(img.resize((W, H), Image.BILINEAR, box=(x0, y0, x0 + w, y0 + h)))

# ---------------------------------------------------------------- overlays
yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); xn, yn = xx / W, yy / H
VIG = (1 - 0.5 * (((xn - .5) * 1.6) ** 2 + ((yn - .5) * 1.1) ** 2)).clip(0.45, 1)[..., None].astype(np.float32)
def blob(cx, cy, r): return np.exp(-(((xn - cx) * W) ** 2 + ((yn - cy) * H) ** 2) / (2 * (r * W) ** 2))
GLOW = (blob(0.05, 0.08, 0.55)[..., None] * np.array([150, 60, 255], np.float32) + blob(0.98, 0.95, 0.6)[..., None] * np.array([60, 255, 130], np.float32)).astype(np.float32)
th = np.arctan2(yy - H / 2, xx - W / 2); rad = np.hypot(xx - W / 2, yy - H / 2) / (H / 2)
RAYS = ((np.sin(th * 14) > 0.15).astype(np.float32) * np.clip(rad * 1.4 - 0.12, 0, 1) * np.clip(1.25 - rad * .6, 0, 1))[..., None].astype(np.float32)
del th, rad, yy, xx
GRAD = (np.linspace(0, 1, W)[:, None] * np.array([92, 240, 122]) + (1 - np.linspace(0, 1, W)[:, None]) * np.array([190, 90, 255])).astype(np.float32)

def star(sz):
    g = np.linspace(-1, 1, sz, dtype=np.float32); X, Y = np.meshgrid(g, g)
    return (np.exp(-np.abs(X * Y) * 70) * np.exp(-(X ** 2 + Y ** 2) * 2.5) + .7 * np.exp(-(X ** 2 + Y ** 2) * 35)).clip(0, 1)[..., None]
STARS = {sz: star(sz) for sz in (36, 56, 84)}
rng = np.random.default_rng(7)
PART = [{"x": rng.random(), "y": rng.random(), "v": 0.03 + 0.05 * rng.random(), "ph": rng.random() * 6.28, "sz": int(rng.choice([36, 56, 84], p=[.5, .35, .15])),
         "c": np.array([[255, 255, 255], [190, 130, 255], [130, 255, 170], [255, 170, 230]][rng.integers(4)], np.float32), "sw": 0.02 + 0.03 * rng.random()} for _ in range(34)]

def add_sprite(f, spr, cx, cy, col, a):
    h, w = spr.shape[:2]; x0, y0 = int(cx - w / 2), int(cy - h / 2)
    xa, ya, xb, yb = max(x0, 0), max(y0, 0), min(x0 + w, W), min(y0 + h, H)
    if xb <= xa or yb <= ya: return
    f[ya:yb, xa:xb] += spr[ya - y0:yb - y0, xa - x0:xb - x0] * col * a

def blend_rgba(f, rgba, cx, cy, amul=1.0):
    """Alpha-composite an RGBA PIL image centred at (cx, cy) onto the float frame."""
    w, h = rgba.size; x0, y0 = int(cx - w / 2), int(cy - h / 2)
    xa, ya, xb, yb = max(x0, 0), max(y0, 0), min(x0 + w, W), min(y0 + h, H)
    if xb <= xa or yb <= ya: return
    r = np.asarray(rgba)[ya - y0:yb - y0, xa - x0:xb - x0].astype(np.float32); a = r[..., 3:4] / 255 * amul
    f[ya:yb, xa:xb] = f[ya:yb, xa:xb] * (1 - a) + r[..., :3] * a

EMO = ImageFont.truetype("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf", 109)
_emo = {}
def emoji(ch, size):
    size = int(round(size / 8) * 8) or 8
    if (ch, size) not in _emo:
        im = Image.new("RGBA", (136, 128), (0, 0, 0, 0)); ImageDraw.Draw(im).text((0, 0), ch, font=EMO, embedded_color=True)
        _emo[(ch, size)] = im.resize((int(136 * size / 128), size), Image.LANCZOS)
    return _emo[(ch, size)]

FONT = "/usr/share/fonts/truetype/ubuntu/UbuntuSans[wdth,wght].ttf"
def font(sz):
    f = ImageFont.truetype(FONT, int(sz)); f.set_variation_by_axes([100, 800]); return f
OUTLINE, GLOWC = (38, 8, 70), (170, 80, 255)
WHITE, LIME, PINK, GOLD = (255, 255, 255), (108, 255, 122), (255, 95, 210), (255, 216, 74)
_cap = {}
def caption_layer(ci, active):
    key = (ci, active)
    if key in _cap: return _cap[key]
    words = CAPS[ci]["words"]; txt = [w["w"].upper() for w in words]; maxw = W * 0.9; size = (230 if len(txt) == 1 else 150) * S * E.get("caption_scale", 1.0)
    while True:
        f = font(size); sw = max(6, int(size * 0.095)); sp = f.getlength(" ") * 0.9
        lines, cur, cw = [], [], 0
        for k, t in enumerate(txt):
            l = f.getlength(t)
            if cur and cw + sp + l > maxw: lines.append(cur); cur, cw = [], 0
            cw += (sp if cur else 0) + l; cur.append(k)
        lines.append(cur)
        if len(lines) <= 2 and max(sum(f.getlength(txt[k]) for k in ln) + sp * (len(ln) - 1) for ln in lines) <= maxw: break
        size -= 6 * S
    lh = size * 1.08; pad = int(sw * 3 + 30); LW, LH = W, int(lh * len(lines) + 2 * pad)
    pos = []
    for li, ln in enumerate(lines):
        tw = sum(f.getlength(txt[k]) for k in ln) + sp * (len(ln) - 1); x = (LW - tw) / 2
        for k in ln: pos.append((k, x, pad + li * lh)); x += f.getlength(txt[k]) + sp
    def draw_pass(layer, fn):
        d = ImageDraw.Draw(layer)
        for k, x, y in pos: fn(d, txt[k], x, y, k)
    glow = Image.new("RGBA", (LW, LH), (0, 0, 0, 0))
    draw_pass(glow, lambda d, t, x, y, k: d.text((x, y), t, font=f, fill=GLOWC + (255,), stroke_width=sw + 10, stroke_fill=GLOWC + (255,)))
    glow = glow.filter(ImageFilter.GaussianBlur(18 * S)); ga = glow.getchannel("A").point(lambda v: min(255, int(v * 1.1))); glow.putalpha(ga)
    shadow = Image.new("RGBA", (LW, LH), (0, 0, 0, 0))
    draw_pass(shadow, lambda d, t, x, y, k: d.text((x, y + 12 * S), t, font=f, fill=(0, 0, 0, 200), stroke_width=sw, stroke_fill=(0, 0, 0, 200)))
    shadow = shadow.filter(ImageFilter.GaussianBlur(6 * S))
    body = Image.new("RGBA", (LW, LH), (0, 0, 0, 0))
    draw_pass(body, lambda d, t, x, y, k: d.text((x, y), t, font=f, fill=OUTLINE + (255,), stroke_width=sw, stroke_fill=OUTLINE + (255,)))
    def fill(d, t, x, y, k):
        em = words[k]["emph"]; col = (PINK if em else LIME) if k == active else (GOLD if em else WHITE)
        d.text((x, y), t, font=f, fill=col + (255,))
    draw_pass(body, fill)
    out = Image.alpha_composite(Image.alpha_composite(glow, shadow), body); _cap[key] = out; return out

def caption_state(t):
    """(chunk index, active word index, age since chunk start) for time t, or None."""
    for ci, c in enumerate(CAPS):
        s = 0.0 if ci == 0 else c["s"]
        nxt = CAPS[ci + 1]["s"] if ci + 1 < len(CAPS) else 1e9
        hold = c.get("hold", 0.28)
        if s <= t < min(c["e"] + hold, nxt):
            act = max([k for k, w in enumerate(c["words"]) if w["s"] <= t] or [0])
            return ci, act, t - s, t - c["words"][act]["s"], c["e"] + hold - t
    return None

def clip_at(t):
    i = min(int(np.searchsorted(starts, t, side="right")) - 1, len(CL) - 1); return i, t - starts[i]

PRE, READERS = {}, {}
def prepare():
    for i, c in enumerate(CL):
        if c["kind"] == "video": PRE[i] = prep_video(i, c); READERS[i] = Reader(PRE[i])
        elif c["src"] not in PRE: PRE[c["src"]] = prep_image(c)
    if not _emo: pass

def drums_on(t): return not (BRK[0] <= t < BRK[1])

def frame(fi):
    t = fi / FPS; ci, lt = clip_at(t); c = CL[ci]; u = lt / c["dur"]
    age = lt                                               # since the cut
    hook = ci == 0
    zc = 1.0; cx = cy = 0.5
    bi = int(t // BEAT); ab = t - bi * BEAT
    punch = (0.05 if bi % 4 == 0 else 0.022) * math.exp(-ab / 0.13) if drums_on(t) else 0.014 * math.sin(t * 2.2)
    cutz = (0.4 if hook else 0.11) * math.exp(-age / (0.16 if hook else 0.12))
    hitz, hitf = 0.0, 0.0
    for h in HITS:
        a = t - h
        if 0 <= a < 0.6: hitz += 0.085 * math.exp(-a / 0.11); hitf += 0.22 * math.exp(-a / 0.07)
    amp = (22 if hook else 13) * S * math.exp(-age / 0.1) + sum(10 * S * math.exp(-(t - h) / 0.08) for h in HITS if 0 <= t - h < 0.3)
    dx, dy = amp * math.sin(age * 95 + 1.3) / W, amp * math.cos(age * 120) / H
    if c["kind"] == "video":
        zc = 1.0 + (0.1 * u if hook else 0.0) if ci == 0 else 1.0 + 0.06 * u
        img = Image.fromarray(READERS[ci].get(int(round(lt * FPS)))); zmb = 1
    else:
        z0, z1 = c.get("zoom", [1.0, 1.1]); zc = lerp(z0, z1, ease_io(u)); img = PRE[c["src"]]; zmb = ZM
    z = zc * (1 + punch + cutz + hitz)
    fr = view(img, z, cx + dx, cy + dy, zmb)
    chroma = int((16 if hook else 9) * S * math.exp(-age / 0.09)) + int(6 * S * hitf)
    if chroma > 0:
        fr = fr.copy(); fr[..., 0] = np.roll(fr[..., 0], chroma, 1); fr[..., 2] = np.roll(fr[..., 2], -chroma, 1)
    f = fr.astype(np.float32) * VIG
    pulse = math.exp(-ab / 0.25) * (1 if drums_on(t) else .5)
    f += GLOW * (0.05 + 0.2 * pulse)
    for p in PART:                                         # sparkles rising with sway, twinkling on beats
        y = (p["y"] - p["v"] * t) % 1.0; x = p["x"] + 0.03 * math.sin(t * 1.3 + p["ph"])
        tw = 0.5 + 0.5 * math.sin(t * 4 + p["ph"] * 3); a = (0.35 + 0.5 * tw) * (1 + 0.8 * pulse)
        add_sprite(f, STARS[p["sz"]], x * W, y * H, p["c"], min(a, 1.2))
    for bt in BURSTS:                                      # radial rays
        a = t - bt
        if 0 <= a < 0.45: f += RAYS * np.array([255, 235, 160], np.float32) * (0.6 * (1 - a / 0.45) ** 2)
    fl = (0.9 * math.exp(-age / 0.09) if ci > 0 or t > 0.0 else 0) + hitf
    if hook: fl = 0.6 * math.exp(-t / 0.07)
    if fl > 0.01: f += (np.array([255, 240, 255], np.float32) - f) * min(fl, 0.95)
    for s in E.get("stickers", []):                        # emoji stickers
        a = t - s["t"]; hold = s.get("hold", 1.3)
        if a < 0 or a > hold + 0.3: continue
        n = s.get("n", 1)
        for k in range(n):
            ak = a - k * 0.09
            if ak < 0: continue
            fade = 1 - ease_io((ak - hold) / 0.25)
            if s.get("kind", "pop") == "pop":
                sc = back(ak / 0.3) * (1 + 0.04 * math.sin(ak * 9)); x, y = s["x"] * W, s["y"] * H + 10 * S * math.sin(ak * 6)
                im = emoji(s["e"], s["size"] * S * sc).rotate(8 * math.sin(ak * 7), expand=True, resample=Image.BICUBIC)
            else:
                r2 = np.random.default_rng(k * 13 + int(s["t"] * 10)); ox = (r2.random() - .5) * 0.7
                x = (s["x"] + ox) * W + 40 * S * math.sin(ak * 4 + k); y = s["y"] * H - ak * (380 + 160 * r2.random()) * S
                im = emoji(s["e"], s["size"] * S * (0.7 + 0.6 * r2.random()) * back(ak / 0.25)); fade *= 1 - 0.6 * ease_io(ak / hold)
            blend_rgba(f, im, x, y, max(fade, 0))
    cs = caption_state(t)
    if cs:
        ci_c, act, cage, wage, left = cs; lay = caption_layer(ci_c, act)
        first = ci_c == 0
        sc = lerp(1.3 if first else 0.55, 1.0, back(cage / (0.22 if first else 0.17))) * (1 + 0.07 * math.exp(-wage / 0.1)) if True else 1
        rot0 = (6 if ci_c % 2 else -6) * (1 - ease_out(cage / 0.2)); al = min(1, (0.6 if first else 0.0) + cage / 0.05, max(left, 0) / 0.08)
        im = lay.resize((int(lay.width * sc), int(lay.height * sc)), Image.BICUBIC).rotate(rot0, expand=True, resample=Image.BICUBIC)
        blend_rgba(f, im, W / 2, H * E.get("caption_y", 0.5) + 8 * S * math.sin(t * 5), al)
    bw = int(W * t / TOTAL)                                # progress bar (top)
    if bw > 0: f[0:int(12 * S), :bw] = GRAD[:bw][None] * (0.85 + 0.3 * pulse)
    return np.clip(f, 0, 255).astype(np.uint8)

# ---------------------------------------------------------------- audio
AR = 48000
def lpf(x, fc, o=2): return lfilter(*butter(o, fc / (AR / 2), "low"), x)
def bpf(x, a, b): return lfilter(*butter(2, [a / (AR / 2), b / (AR / 2)], "band"), x)
def tt(d): return np.arange(int(d * AR)) / AR
def sfx_wave(k, r):
    if k == "impact":
        t = tt(0.9); x = np.sin(2 * np.pi * np.cumsum(38 + 90 * np.exp(-t * 14)) / AR) * np.exp(-t * 4.5) * 1.1
        x += lpf(r.standard_normal(len(t)), 900) * np.exp(-t * 12) * 0.6 + bpf(r.standard_normal(len(t)), 2500, 9000) * np.exp(-t * 30) * 0.35
        return x
    if k == "whoosh":                                        # three noise bands swelling one after another = rising sweep
        t = tt(0.42); n = r.standard_normal(len(t)); u = t / 0.42; y = 0
        for (lo, hi), pk, g in (((300, 1200), .3, 1.0), ((1200, 4000), .6, 1.0), ((4000, 12000), .85, 0.8)): y = y + bpf(n, lo, hi) * np.exp(-((u - pk) / .18) ** 2) * g
        return y * 2.2
    if k == "pop":
        t = tt(0.12); return np.sin(2 * np.pi * np.cumsum(500 + 900 * np.exp(-t * 35)) / AR) * np.exp(-t * 28) * 0.8
    if k == "tick":
        t = tt(0.04); return bpf(r.standard_normal(len(t)), 2000, 8000) * np.exp(-t * 90) * 0.7
    if k == "chirp":
        x = np.zeros(int(0.5 * AR))
        for o in (0.0, 0.17):
            t = tt(0.14); f = 900 + 900 * np.sin(np.pi * t / 0.14 * 0.5 + 0) + 500 * t / 0.14
            w = np.sin(2 * np.pi * np.cumsum(f) / AR) * np.sin(np.pi * t / 0.14) ** 0.6 * 0.6; i = int(o * AR); x[i:i + len(w)] += w
        return x
    if k == "sparkle":
        x = np.zeros(int(1.4 * AR))
        for j, m in enumerate((84, 88, 91, 96, 100)):
            t = tt(1.0); f = 440 * 2 ** ((m - 69) / 12); w = (np.sin(2 * np.pi * f * t) + .3 * np.sin(2 * np.pi * f * 2.76 * t)) * np.exp(-t * 6) * 0.35
            i = int(j * 0.06 * AR); x[i:i + len(w)] += w[:len(x) - i]
        return x
    if k == "growl":                                         # rumble with fast tremolo = "grrr"
        t = tt(0.9); env = np.sin(np.pi * t / 0.9) ** 0.7; x = np.sin(2 * np.pi * np.cumsum(70 + 25 * np.sin(t * 9)) / AR) * (0.55 + 0.45 * np.sin(2 * np.pi * 28 * t))
        x += lpf(r.standard_normal(len(t)), 500) * 0.8 * (0.6 + 0.4 * np.sin(2 * np.pi * 28 * t)); return x * env * 0.9
    if k == "squeak":                                        # cute rising squeak
        t = tt(0.22); f = 900 + 1500 * (t / 0.22) ** 0.6; return np.sin(2 * np.pi * np.cumsum(f) / AR) * np.sin(np.pi * t / 0.22) ** 0.5 * 0.7
    if k == "ding":
        t = tt(1.6); return sum(a * np.sin(2 * np.pi * f * t) * np.exp(-t * d) for f, a, d in ((1318, 1, 2.5), (1318 * 2.76, .4, 5), (1318 * 5.4, .2, 8))) * 0.4
    raise ValueError(k)

def build_audio():
    r = np.random.default_rng(3); N = int(TOTAL * AR)
    vo, sr = sf.read(P("audio/voice.wav")); vo = resample_poly(vo.astype(np.float32), AR, sr)[:N]; vo = np.pad(vo, (0, N - len(vo)))
    vo = lfilter(*butter(2, 90 / (AR / 2), "high"), vo); act = np.abs(vo) > 1e-3
    rms = np.sqrt(np.mean(vo[np.abs(vo) > 0.02] ** 2)); vo = vo * (10 ** (E.get("voice_db", -17) / 20) / rms)
    mu, sr = sf.read(P("audio/music.wav")); mu = mu if mu.ndim == 1 else mu.mean(1); mu = resample_poly(mu.astype(np.float32), AR, sr)[:N]; mu = np.pad(mu, (0, N - len(mu)))
    mu = mu * (10 ** (E.get("music_db", -21) / 20) / np.sqrt(np.mean(mu ** 2)))
    env = lfilter([1 / 2400.0] * 2400, [1], np.abs(vo)); speaking = (env > 0.012).astype(np.float32)   # 50 ms window
    duck = lfilter([0.002], [1, -0.998], speaking)                                                     # slow release (~0.4 s)
    duck = np.maximum(duck, lfilter([0.03], [1, -0.97], speaking)); duck = np.clip(duck, 0, 1)
    mu = mu * (1 - duck * (1 - 10 ** (E.get("duck_db", -13) / 20)))
    sx = np.zeros(N)
    def put(k, t, g=1.0):
        w = sfx_wave(k, r) * g; i = int(t * AR)
        if i < 0: w, i = w[-i:], 0
        e = min(N, i + len(w)); sx[i:e] += w[:e - i]
    put("impact", 0.0, 0.55)
    for st in starts[1:-1]: put("whoosh", st - 0.2, 0.22)
    for h in HITS: put("tick", h, 0.25)
    for s in E.get("sfx", []): put(s["k"], s["t"], s.get("g", 0.4))
    mix = vo + mu + sx * 0.6
    fade = int(E.get("fade_out", 0.25) * AR); mix[-fade:] *= np.linspace(1, 0, fade)
    mix = np.tanh(mix * 0.85) / np.tanh(0.85); mix = mix / max(np.abs(mix).max(), 1e-6) * 0.93
    sf.write(P("audio/mix.wav"), np.stack([mix, mix], 1).astype(np.float32), AR)
    print("audio/mix.wav: voz", round(20 * np.log10(np.sqrt(np.mean((vo[act]) ** 2))), 1), "dBFS rms, música media", round(20 * np.log10(np.sqrt(np.mean(mu ** 2))), 1), "dBFS")

# ---------------------------------------------------------------- run
def encode(f0, f1, out, audio=True):
    fps = str(CFG["fps"]); cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", fps, "-i", "-"]
    if audio: cmd += ["-ss", f"{f0 / FPS:.4f}", "-t", f"{(f1 - f0) / FPS:.4f}", "-i", P("audio/mix.wav")]
    cmd += video_encoder_args(PR.machine, CFG["nvenc_cq"]) + ["-pix_fmt", "yuv420p", "-r", fps]
    cmd += (["-c:a", "aac", "-b:a", CFG["audio_bitrate"], "-shortest"] if audio else ["-an"]) + ["-movflags", "+faststart", out]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for fi in range(f0, f1):
        p.stdin.write(frame(fi).tobytes())
        if fi % 150 == 0: print(f"  frame {fi}/{NF}", flush=True)
    p.stdin.close(); p.wait()

if A.audio: build_audio(); sys.exit()
prepare()
if A.frame:
    for t in A.frame:
        Image.fromarray(frame(min(int(round(t * FPS)), NF - 1))).save(PR.rdir(f"frame_{t:06.2f}.png")); print("render/frame_%06.2f.png" % t)
elif A.preview:
    build_audio(); f0, f1 = int(A.preview[0] * FPS), min(int(A.preview[1] * FPS), NF); encode(f0, f1, P("out/preview.mp4")); print("out/preview.mp4")
else:
    build_audio(); out = PR.output; encode(0, NF, out); print(out)
for r in READERS.values(): r.close()
