# Lyric video renderer: procedural scenes (engine/scenes + optional <project>/scenes.py) + karaoke lyrics.
# H.264 encoder = the best one that works on this machine (settings.local.json -> machine.video_encoder).
#   python engine/render.py <project> --frame 60.2 [..]     -> render/frame_060.20.png (stills for checks)
#   python engine/render.py <project> --preview 119.5 139.5 -> out/preview.mp4
#   python engine/render.py <project> [--force]             -> render/seg_*.mp4 (resumable) + out/<output>
# Inputs (project folder): config.json, storyboard.json, audio/beats.json, lyrics/lyrics.json
# --force discards cached segments (needed after editing lyrics/storyboard/config/scenes).
import argparse, json, math, os, subprocess, sys
from multiprocessing import Pool
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from common import project_from_argv, audio_codec, video_encoder_args
from engine import timing, scenes as scene_lib
from engine.timing import snap, pulse, en

PR = project_from_argv()
CFG = PR.cfg
P = PR.p
W, H, FPS = CFG["width"], CFG["height"], CFG["fps"]
BW, BH = CFG.get("scene_canvas") or (540, 960)   # scene design canvas (default vertical 540x960; e.g. [540, 540] for 1:1). Same aspect as output = plain upscale;
VERTICAL = abs(W / H - BW / BH) < 0.01   # other formats: scene centred over a blurred, enlarged copy of itself
S = min(W, H) / 1080         # text scale relative to the 1080-wide design
SEG = CFG["segment_seconds"]

BEATS = json.load(open(P("audio/beats.json")))
LYR = json.load(open(P("lyrics/lyrics.json"))) if os.path.exists(P("lyrics/lyrics.json")) else {"language": None, "lines": []}   # instrumental: no lyrics
LINES = LYR["lines"]
SB = json.load(open(P("storyboard.json")))
DUR = BEATS["duration"]
NFRAMES = math.ceil(DUR * FPS)
timing.init(BEATS, FPS)
beats, downs = timing.beats, timing.downs
BG = CFG["background"]
VIDEO_BG = BG.get("type") == "video"
VOX_BG = BG.get("type") == "voxels"   # 3D voxel realms (engine/voxel), scenes in <project>/voxscenes.py
SCENES = {} if VIDEO_BG or VOX_BG else scene_lib.load(PR.dir, BW, BH, CFG["palette"])

MODE = CFG["lyrics_mode"]
if MODE == "auto":
    MODE = {"es": "orig", "en": "orig+es"}.get(LYR.get("language"), "orig+rom+es")

# ---------------------------------------------------------------- timing
SECTIONS = SB.get("sections", [{"start": 0.0, "name": "all", "kind": "verse"}])
def section_at(t):
    s = SECTIONS[0]
    for x in SECTIONS:
        if x["start"] <= t: s = x
    return s

TL = json.load(open(P("audio/timeline.json"))) if os.path.exists(P("audio/timeline.json")) else None   # narrated stories
PAUSES = TL["pauses"] if TL else []

def block_start(b):
    """Block start: "start" (s), "para" (story paragraph; a part's first paragraph starts mid-pause) or "line" (caption index)."""
    if "start" in b: t = b["start"]
    elif "para" in b:
        pi = next((i for i, p in enumerate(TL["parts"]) if p["paras"] == b["para"]), None) if TL else None
        if pi is not None: t = 0.0 if pi == 0 else (PAUSES[pi - 1]["start"] + PAUSES[pi - 1]["end"]) / 2
        else: t = next(l["start"] for l in LINES if l.get("para") == b["para"]) - 0.15
    else: t = LINES[b["line"]]["start"] - 0.15
    return max(0.0, t + b.get("offset", 0))

def build_cuts():
    blocks = SB["blocks"]
    bst = [block_start(b) for b in blocks]
    starts = [0.0 if t == 0 else snap(t, beats) for t in bst] + [DUR]
    sec_starts = {round(s["start"], 1) for s in SECTIONS}
    cuts = []
    for i, b in enumerate(blocks):
        t, end, v = starts[i], starts[i + 1], 0
        while True:
            hard = v == 0 and t > 0 and round(bst[i], 1) in sec_starts and section_at(bst[i])["kind"] in ("chorus", "pre", "verse", "outro")
            cuts.append({"t": t, "motif": b["motif"], "v": v, "hard": hard, "bstart": starts[i], "blk": b})
            nxt = t + b.get("cut_every", 2.0)
            d = snap(nxt, downs)
            nxt = d if abs(d - nxt) <= 0.45 else snap(nxt, beats)
            ce = b.get("cut_every", 2.0); mn = min(1.0, ce * 0.5)
            if nxt <= t + mn: nxt = t + max(ce, 2.0 if ce >= 2.0 else mn * 2)     # past the last beat: keep advancing
            if nxt > end - mn: break
            t, v = nxt, v + 1
    return cuts
CUTS = [] if VIDEO_BG or VOX_BG else build_cuts()
CUT_T = np.array([c["t"] for c in CUTS])
missing = {c["motif"] for c in CUTS} - set(SCENES)
if missing: sys.exit(f"storyboard uses unknown motifs {missing}; available: {sorted(SCENES)}")

# vignette (bg resolution)
_yy, _xx = np.mgrid[0:BH, 0:BW]
VIG = (1 - 0.55 * (((_xx - BW / 2) / (BW * 0.75)) ** 2 + ((_yy - BH / 2) / (BH * 0.75)) ** 2)).clip(0.35, 1)[..., None].astype(np.float32)

def draw_cut(ci, t):
    cut = CUTS[ci]
    lt = t - cut["t"]
    arr = SCENES[cut["motif"]](t, lt, cut["v"], pulse(t), en(t), t - cut["bstart"], cut["blk"])
    return np.asarray(arr, np.float32)

def pause_amount(t):
    """0..1 blur/dim for the breathing pauses between story parts (eases in before, out after)."""
    for p in PAUSES:
        a, b = p["start"] - 0.45, p["end"] + 0.45
        if a <= t <= b:
            u = min((t - a) / 0.75, (b - t) / 0.75, 1.0)
            return u * u * (3 - 2 * u)
    return 0.0

TRANS = CFG.get("transitions")
TR_DUR = 0.3
def _zoom(a, z):
    """Zoom a float image about its centre (z > 1 enlarges)."""
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)); w, h = BW / z, BH / z
    return np.asarray(im.resize((BW, BH), Image.BILINEAR, box=((BW - w) / 2, (BH - h) / 2, (BW + w) / 2, (BH + h) / 2)), np.float32)

def transition(kind, a, b, u, ci):
    """Blend the previous scene a into the new one b, u = 0..1 over TR_DUR. Each style is an attention-grabbing pattern interrupt."""
    e = 1 - (1 - u) ** 3
    if kind == "flash":
        k = min(1.0, u * 4)
        return (a * (1 - k) + b * k) + (255 - b) * 0.85 * (1 - u) ** 2
    if kind == "glitch":
        out = (a if u < 0.3 else b).copy()
        sh = int(36 * (1 - u))
        out[..., 0] = np.roll(out[..., 0], sh, 1); out[..., 2] = np.roll(out[..., 2], -sh, 1)
        r = np.random.default_rng(ci * 31 + int(u * 8))
        for _ in range(7):
            y0 = int(r.integers(0, BH - 40)); hh = int(r.integers(8, 50)); dx = int(r.integers(-60, 60) * (1 - u))
            out[y0:y0 + hh] = np.roll(out[y0:y0 + hh], dx, 1)
        return out
    if kind == "slide":
        off = int(BW * e)
        if ci % 2: return np.concatenate([a, b], 1)[:, off:off + BW]
        return np.concatenate([b, a], 1)[:, BW - off:2 * BW - off]
    if kind == "zoom":
        k = min(1.0, u * 2.2)
        return _zoom(a, 1 + 1.4 * e) * (1 - k) + _zoom(b, 1 + 0.5 * (1 - e)) * k
    if kind == "iris":
        yy, xx = np.ogrid[0:BH, 0:BW]
        rad = e * math.hypot(BW, BH) / 2 * 1.05
        m = ((xx - BW / 2) ** 2 + (yy - BH / 2) ** 2 <= rad * rad)[..., None]
        ring = (np.abs(np.sqrt((xx - BW / 2) ** 2 + (yy - BH / 2) ** 2) - rad) < 7)[..., None] * 255
        return np.where(m, b, a) + ring * (1 - u)
    if kind == "whip":
        n, sh = 7, int(110 * (1 - abs(2 * u - 1)) + 4)
        src = a if u < 0.5 else b
        return sum(np.roll(src, int(sh * (i / n - 0.5)) * (1 if ci % 2 else -1), 1) for i in range(n)) / n
    if kind == "bars":
        k = int(BW / 9)
        idx = (np.arange(BW) // k) % 2
        prog = np.where(idx == 0, e, np.clip(e * 1.6 - 0.3, 0, 1))
        cols = (np.arange(BW) % k) / k < prog
        return np.where(cols[None, :, None], b, a)
    return a * (1 - u) + b * u

def background(t):
    ci = max(0, int(np.searchsorted(CUT_T, t, side="right") - 1))
    cut = CUTS[ci]
    lt = t - cut["t"]
    img = draw_cut(ci, t)
    kind = section_at(t)["kind"]
    zoom_punch = 0.0
    if cut["hard"]:
        zoom_punch = 0.14 * math.exp(-lt / 0.25)
        img = img + (255 - img) * (0.6 * math.exp(-lt / 0.12))            # flash
    elif ci > 0 and TRANS and lt < TR_DUR:
        img = transition(TRANS[ci % len(TRANS)], draw_cut(ci - 1, t), img, lt / TR_DUR, ci)
    elif ci > 0 and not TRANS and lt < 0.2:
        k = lt / 0.2
        img = draw_cut(ci - 1, t) * (1 - k) + img * k                         # soft cross-dissolve
    img = img * VIG
    if CFG["beat_fx"]:
        sh = int(round(3 * pulse(t) ** 1.5))
        if sh: img = img.copy(); img[..., 0] = np.roll(img[..., 0], sh, 1); img[..., 2] = np.roll(img[..., 2], -sh, 1)
    fo = CFG["fade_out"]
    if fo and t > DUR - fo - 0.25:
        img = img * max(0.0, 1 - (t - (DUR - fo - 0.25)) / fo)
    k = pause_amount(t)
    if k > 0: img = img * (1 - 0.6 * k)
    im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    if k > 0.02: im = im.filter(ImageFilter.GaussianBlur(16 * k))
    p = pulse(t)
    z = 1.05 + (0.035 if kind == "chorus" else 0.015) * p + 0.02 * math.sin(lt * 0.9 + cut["v"]) + zoom_punch
    drift = (cut["v"] % 3 - 1) * 8 * lt / 2
    w, h = BW / z, BH / z
    x0, y0 = (BW - w) / 2 + drift, (BH - h) / 2 + 6 * math.sin(lt)
    x0 = min(max(0, x0), BW - w); y0 = min(max(0, y0), BH - h)
    if VERTICAL:
        return im.resize((W, H), Image.BILINEAR, box=(x0, y0, x0 + w, y0 + h))
    fh = H; fw = int(fh * BW / BH)
    if fw > W: fw = W; fh = int(fw * BH / BW)
    cw = max(W / BW, H / BH)                                   # cover scale for the backdrop
    back = im.resize((int(BW * cw / 4), int(BH * cw / 4)), Image.BILINEAR).filter(ImageFilter.GaussianBlur(6))
    back = Image.eval(back.resize((int(BW * cw), int(BH * cw)), Image.BILINEAR), lambda c: int(c * 0.55))
    out = back.crop(((back.width - W) // 2, (back.height - H) // 2, (back.width - W) // 2 + W, (back.height - H) // 2 + H))
    out.paste(im.resize((fw, fh), Image.BILINEAR, box=(x0, y0, x0 + w, y0 + h)), ((W - fw) // 2, (H - fh) // 2))
    return out

# ---------------------------------------------------------------- lyrics
FONT_B, FONT_R, FI = CFG["font_bold"], CFG["font_regular"], CFG["font_index"]
TC = {k: tuple(v) for k, v in CFG["text_colors"].items()}
MAXW = int(W - 160 * S)
TSZ = CFG["text_size"]
font = lambda path, size: ImageFont.truetype(path, max(8, int(size * S)), index=FI)

class LineGfx:
    def __init__(self, L):
        self.L = L
        words = [w["w"] for w in L["words"]]
        size = TSZ
        while True:
            f = font(FONT_B, size)
            sp = f.getlength(" ")
            wl = [f.getlength(w) for w in words]
            if sum(wl) + sp * (len(words) - 1) <= MAXW or size <= TSZ * 0.76: break
            size -= 4
        rows = [list(range(len(words)))]
        if sum(wl) + sp * (len(words) - 1) > MAXW:     # wrap in 2 balanced rows
            best = None
            for cut in range(1, len(words)):
                a = sum(wl[:cut]) + sp * (cut - 1); b = sum(wl[cut:]) + sp * (len(words) - cut - 1)
                if best is None or max(a, b) < best[0]: best = (max(a, b), cut)
            rows = [list(range(best[1])), list(range(best[1], len(words)))]
        fs, fe = font(FONT_R, 44 * TSZ / 92), font(FONT_R, 46 * TSZ / 92)
        subs = []
        if "rom" in MODE and L.get("rom"): subs.append((L["rom"], fs, TC["rom"]))
        if "es" in MODE and L.get("es"): subs.append((L["es"], fe, TC["tr"]))
        subs = [(self.fit(s, f, MAXW), f, c) for s, f, c in subs]
        mh = int(f.size * 1.28)
        sh = [int(f.size * 1.4) * len(s) for s, f, c in subs]
        pad = int(50 * S)
        bh = mh * len(rows) + int(18 * S) + sum(sh) + pad * 2
        self.w, self.h = W, bh
        base = Image.new("RGBA", (W, bh)); sung = Image.new("RGBA", (W, bh)); gl = Image.new("RGBA", (W, bh))
        db, ds, dg = ImageDraw.Draw(base), ImageDraw.Draw(sung), ImageDraw.Draw(gl)
        self.boxes = []
        y = pad
        for row in rows:
            rw = sum(wl[i] for i in row) + sp * (len(row) - 1)
            x = (W - rw) / 2
            for i in row:
                db.text((x, y), words[i], font=f, fill=TC["unsung"] + (215,), stroke_width=int(6 * S), stroke_fill=TC["outline"] + (235,))
                ds.text((x, y), words[i], font=f, fill=TC["sung"] + (255,), stroke_width=int(6 * S), stroke_fill=TC["outline"] + (255,))
                ds.text((x, y), words[i], font=f, fill=TC["sung"] + (255,))
                dg.text((x, y), words[i], font=f, fill=TC["glow"] + (255,), stroke_width=int(10 * S), stroke_fill=TC["glow"] + (255,))
                self.boxes.append((x - 8 * S, y - 10 * S, x + wl[i] + 8 * S, y + mh))
                x += wl[i] + sp
            y += mh
        y += int(18 * S)
        for lines, fnt, col in subs:
            for s in lines:
                lw = fnt.getlength(s)
                db.text(((W - lw) / 2, y), s, font=fnt, fill=col + (255,), stroke_width=int(4 * S), stroke_fill=TC["outline"] + (240,))
                y += int(fnt.size * 1.4)
        # subtle dark panel behind the text for contrast on bright scenes
        tb = base.getbbox() or (0, 0, W, bh)
        panel = Image.new("RGBA", (W, bh))
        ImageDraw.Draw(panel).rounded_rectangle([tb[0] - 40 * S, tb[1] - 26 * S, tb[2] + 40 * S, tb[3] + 26 * S], int(48 * S), fill=TC["panel"])
        panel = panel.filter(ImageFilter.GaussianBlur(18 * S))
        self.base = Image.alpha_composite(panel, base)
        self.sung = sung
        self.glow = gl.filter(ImageFilter.GaussianBlur(16 * S))

    @staticmethod
    def fit(s, f, maxw):
        if f.getlength(s) <= maxw: return [s]
        ws = s.split(); best = None
        for c in range(1, len(ws)):
            a, b = " ".join(ws[:c]), " ".join(ws[c:])
            m = max(f.getlength(a), f.getlength(b))
            if best is None or m < best[0]: best = (m, [a, b])
        return best[1]

    def render(self, t, kind):
        L = self.L
        mask = Image.new("L", (self.w, self.h))
        md = ImageDraw.Draw(mask)
        active = None
        for w, (x0, y0, x1, y1) in zip(L["words"], self.boxes):
            if t >= w["e"]: md.rectangle([x0, y0, x1, y1], fill=255)
            elif t >= w["s"]:
                k = (t - w["s"]) / max(0.05, w["e"] - w["s"])
                md.rectangle([x0, y0, x0 + (x1 - x0) * k, y1], fill=255); active = (x0, y0, x1, y1)
        img = self.base.copy()
        gk = {"chorus": 1.0, "pre": 0.8}.get(kind, 0.6)
        gmask = mask.point(lambda a: int(a * gk))
        img.paste(self.glow, (0, 0), Image.fromarray(np.minimum(np.asarray(gmask), np.asarray(self.glow)[..., 3]).astype(np.uint8)))
        img = Image.alpha_composite(img, Image.composite(self.sung, Image.new("RGBA", img.size), mask))
        return img

GFX = {}
def gfx(i):
    if i not in GFX: GFX[i] = LineGfx(LINES[i])
    return GFX[i]

def lyrics_layers(t):
    out = []
    for i, L in enumerate(LINES):
        s, e = L["start"], L["end"]
        nxt = LINES[i + 1]["start"] if i + 1 < len(LINES) else 1e9
        fin = min(0.08, max(0.0, s - (LINES[i - 1]["end"] if i else -1)))      # fade-in window, never before prev end
        fout_end = min(e + 0.15, nxt)
        if t < s - fin or t > fout_end: continue
        a = 1.0
        if t < s: a = (t - (s - fin)) / max(fin, 1e-3)
        elif t > e: a = 1 - (t - e) / max(fout_end - e, 1e-3)
        out.append((i, max(0.0, min(1.0, a)), t - s))
    return out

def video_reader(f0):
    """Background video from frame f0: scaled/cropped to the output size, under a black cover (background.dim)."""
    vf = f"fps={FPS},scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1"
    if BG.get("dim", 0.6): vf += f",drawbox=x=0:y=0:w=iw:h=ih:color=black@{BG.get('dim', 0.6)}:t=fill"
    return subprocess.Popen(["ffmpeg", "-loglevel", "error", "-ss", f"{float(f0 / FPS):.4f}", "-i", P(BG["source"]), "-an", "-vf", vf,
                             "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)

_SHOW = None
def vox_show():
    """Created lazily in each worker process (an EGL context must not cross a fork)."""
    global _SHOW
    if _SHOW is None:
        from engine.voxel.show import Show
        _SHOW = Show(PR, BEATS, SB, W, H, FPS)
    return _SHOW

def frame(fi, bg=None):
    t = float(fi / FPS)
    if bg is None and VOX_BG:
        bg = Image.frombytes("RGB", (W, H), vox_show().frame(t)).transpose(Image.FLIP_TOP_BOTTOM)
    img = (bg if bg is not None else background(t)).convert("RGBA")
    kind = section_at(t)["kind"]
    p = pulse(t)
    for i, a, since in lyrics_layers(t):
        g = gfx(i)
        layer = g.render(t, kind)
        sc = 1 + ((0.045 if kind == "chorus" else 0.015) * p if CFG["text_pulse"] else 0)
        if since < 0.25: sc *= 0.94 + 0.06 * (1 - (1 - max(0, since) / 0.25) ** 3)   # ease-in pop
        dx = dy = 0.0; ang = 0.0
        if CFG["text_anim"] == "dynamic":
            u = max(0.0, min(1.0, since / 0.24)); e3 = 1 - (1 - u) ** 3; st = i % 4
            if st == 0: sc *= 1 + 0.7 * (1 - e3)
            elif st == 1: dy = 150 * S * (1 - e3)
            elif st == 2: ang = 14 * (1 - e3); sc *= 0.7 + 0.3 * e3
            else: dy = -150 * S * (1 - e3); sc *= 1.15 - 0.15 * e3
            if t > LINES[i]["end"]: sc *= 1 + 0.35 * min(1.0, (t - LINES[i]["end"]) / 0.15)
        if abs(sc - 1) > 0.002:
            layer = layer.resize((int(g.w * sc), int(g.h * sc)), Image.BILINEAR)
        if ang: layer = layer.rotate(ang * (1 if i % 8 < 4 else -1), expand=True, resample=Image.BILINEAR)
        if a < 1:
            al = np.asarray(layer).copy(); al[..., 3] = (al[..., 3] * a).astype(np.uint8); layer = Image.fromarray(al)
        cy = H * 0.8 if CFG["caption_position"] == "bottom" else H / 2
        img.alpha_composite(layer, (int((W - layer.width) // 2 + dx), int(cy - layer.height / 2 + dy)))
    return img.convert("RGB")

# ---------------------------------------------------------------- encode
def ff_writer(path):
    return subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                             *video_encoder_args(PR.machine, CFG["nvenc_cq"]), "-pix_fmt", "yuv420p", path], stdin=subprocess.PIPE)

def render_range(args):
    f0, f1, path = args
    tmp = path + ".part.mp4"
    pr = ff_writer(tmp)
    rd = video_reader(f0) if VIDEO_BG else None
    last = None
    for fi in range(f0, f1):
        bg = None
        if rd:
            buf = rd.stdout.read(W * H * 3)
            if len(buf) == W * H * 3: last = Image.frombytes("RGB", (W, H), buf)
            bg = last if last is not None else Image.new("RGB", (W, H))   # source shorter than audio: hold last frame
        pr.stdin.write(frame(fi, bg).tobytes())
    pr.stdin.close(); pr.wait()
    if rd: rd.kill(); rd.wait()
    os.replace(tmp, path)
    return path

def mux(video, out, t0=0.0, dur=None):
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", video, "-ss", f"{t0:.3f}"] + (["-t", f"{dur:.3f}"] if dur else []) + \
          ["-i", PR.audio, "-map", "0:v", "-map", "1:a", "-c:v", "copy"] + (["-c:a", "copy"] if audio_codec(PR.audio) == "aac" and not dur else ["-c:a", "aac", "-b:a", CFG["audio_bitrate"]]) + ["-movflags", "+faststart", out]
    subprocess.run(cmd, check=True)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", nargs=2, type=float)
    ap.add_argument("--frame", type=float, nargs="+")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--jobs", type=int, default=CFG["jobs"])
    a = ap.parse_args()
    os.makedirs(P("out"), exist_ok=True)
    if a.frame:
        for t in a.frame:
            fi = int(round(t * FPS)); bg = None
            if VIDEO_BG:
                rd = video_reader(fi); bg = Image.frombytes("RGB", (W, H), rd.stdout.read(W * H * 3)); rd.kill()
            frame(fi, bg).save(PR.rdir(f"frame_{t:06.2f}.png")); print("saved", t)
        sys.exit()
    if a.preview:
        t0, t1 = a.preview
        f0, f1 = int(t0 * FPS), int(t1 * FPS)
        n = max(1, a.jobs)
        step = math.ceil((f1 - f0) / n)
        parts = [(s, min(f1, s + step), PR.rdir(f"preview_{i:02d}.mp4")) for i, s in enumerate(range(f0, f1, step))]
        with Pool(n) as pool: pool.map(render_range, parts)
        lst = PR.rdir("preview_list.txt")
        open(lst, "w").write("".join(f"file '{x[2]}'\n" for x in parts))
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", PR.rdir("preview_v.mp4")], check=True)
        mux(PR.rdir("preview_v.mp4"), PR.out_name("preview.mp4"), float(f0 / FPS), float((f1 - f0) / FPS))
        print("out/preview.mp4"); sys.exit()
    segs = []
    for i, f0 in enumerate(range(0, NFRAMES, int(round(SEG * FPS)))):
        path = PR.rdir(f"seg_{i:03d}.mp4")
        if a.force and os.path.exists(path): os.remove(path)
        segs.append((f0, min(NFRAMES, f0 + int(round(SEG * FPS))), path))
    todo = [s for s in segs if not os.path.exists(s[2])]
    print(f"{len(segs)} segments, {len(todo)} to render, {NFRAMES} frames")
    with Pool(a.jobs) as pool:
        for pth in pool.imap_unordered(render_range, todo): print("done", os.path.basename(pth), flush=True)
    lst = PR.rdir("segments.txt")
    open(lst, "w").write("".join(f"file '{s[2]}'\n" for s in segs))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", PR.rdir("full_v.mp4")], check=True)
    mux(PR.rdir("full_v.mp4"), PR.output)
    print(PR.output)
