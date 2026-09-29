# Voxel show timeline: every visual parameter as a pure function of t (scene A -> B morph, looks, smoothed camera,
# audio envelopes, fades, shock rings). Scenes come from the project's voxscenes.py; times from storyboard.json.
import importlib.util, json, math, os
import numpy as np

LOOK_KEYS = ["zen", "hor", "sunDir", "sunCol", "sunI", "amb", "fog", "fogD", "fogH", "fogF", "floor", "mtn", "mtnH",
             "clouds", "stars", "sunVis", "exp", "glow", "bloom", "rays", "magic"]
DEFAULT_LOOK = dict(zen="#2a2238", hor="#c08a5a", sunDir=[-.4, .35, .8], sunCol="#ffd8a0", sunI=1.0, amb="#8a7a78",
                    fog="#b89070", fogD=.003, fogH=-2, fogF=.08, floor="#6a5040", mtn="#5a4436", mtnH=.06,
                    clouds=.6, stars=0, sunVis=1, exp=1.0, glow=.85, bloom=.45, rays=.35, magic="#ffb060")

def _c(v):
    if isinstance(v, str):
        h = v.lstrip("#"); return np.array([(int(h[i:i + 2], 16) / 255) ** 2.2 for i in (0, 2, 4)])
    return np.array(v, float)

def load_scenes(pr):
    path = pr.p(pr.cfg["background"].get("scenes", "voxscenes.py"))
    spec = importlib.util.spec_from_file_location("voxscenes", path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod

def env(a, decay):
    o = np.zeros_like(a); e = 0.0
    for i, x in enumerate(a): e = max(x, e * decay); o[i] = e
    return o

class Show:
    def __init__(self, pr, beats, sb, W, H, fps):
        self.pr, self.W, self.H = pr, W, H
        self.mod = load_scenes(pr)
        self.meta = json.load(open(pr.p("render", "voxcache", "meta.json")))
        names = [s["name"] for s in self.mod.SCENES]
        self.looks = [{**DEFAULT_LOOK, **s.get("look", {})} for s in self.mod.SCENES]
        self.cams = [s["cam"] for s in self.mod.SCENES]
        self.dur = beats["duration"]
        B = np.array(beats["beats"]); self.beats = B
        self.bstr = np.array(beats.get("beat_strength", [1.0] * len(B)))
        downs = np.array(beats["downbeats"])
        snap = lambda t: float(downs[np.argmin(np.abs(downs - t))])
        self.starts = [0.0 if b["start"] == 0 else snap(b["start"]) for b in sb["blocks"]]
        self.idx = [names.index(b["motif"]) for b in sb["blocks"]]
        self.accents = [snap(a) for a in sb.get("accents", [])]
        spb = 60 / beats["tempo"]
        self.ttr = sb.get("transition_beats", 8) * spb
        self.intro = sb.get("intro_assemble", 7.5)
        self.outro = sb.get("outro_dissolve", 8.0)
        self.fade_in, self.fade_out = sb.get("fade_in", 2.2), sb.get("fade_out", 4.5)
        f = beats["bands"]; self.fps_b = beats["bands_fps"]
        g = lambda k: np.array(f[k], np.float32) / 255
        self.aud = {"bass": env(g("bass"), .87), "mid": env((g("lowmid") + g("highmid")) / 2, .9), "high": env(g("high"), .85),
                    "rms": np.convolve(g("rms"), np.ones(25) / 25, "same")}
        self.R, self.vs, self.N = self.meta["R"], self.meta["vs"], self.meta["N"]
        self.renderer = None; self.packs = {}

    # ------------------------------------------------------------ timeline
    def scene_at(self, t):
        return max(0, int(np.searchsorted(self.starts, t, side="right") - 1))

    def pair(self, t):
        """(key A, key B, morph 0..1)"""
        if t >= self.dur - self.outro:
            return self.idx[-1], "dust_up", min(1.0, (t - (self.dur - self.outro)) / self.outro)
        k = self.scene_at(t)
        if k == 0: return "dust", self.idx[0], min(1.0, t / self.intro)
        return self.idx[k - 1], self.idx[k], min(1.0, (t - self.starts[k]) / self.ttr)

    def look(self, t):
        a, b, m = self.pair(t)
        if a in ("dust",): a = b
        if b in ("dust_up",): b = a
        e = m * m * (3 - 2 * m)
        la, lb = self.looks[a], self.looks[b]
        out = {}
        for k in LOOK_KEYS:
            va, vb = _c(la[k]) if k in ("zen", "hor", "sunCol", "amb", "fog", "floor", "mtn", "magic") else np.array(la[k], float), \
                     _c(lb[k]) if k in ("zen", "hor", "sunCol", "amb", "fog", "floor", "mtn", "magic") else np.array(lb[k], float)
            out[k] = va + (vb - va) * e
        return out

    def cam_raw(self, t):
        t = min(max(t, 0.0), self.dur)
        k = self.scene_at(t)
        s = self.starts; end = lambda i: s[i + 1] if i + 1 < len(s) else self.dur
        u = (t - s[k]) / (end(k) - s[k])
        p, q = map(np.array, self.cams[self.idx[k]](u))
        if k > 0 and t - s[k] < self.ttr:
            w = (t - s[k]) / self.ttr; w = w ** 3 * (w * (w * 6 - 15) + 10)
            up = min(1.3, (t - s[k - 1]) / (end(k - 1) - s[k - 1]))
            p0, q0 = map(np.array, self.cams[self.idx[k - 1]](up))
            p = p0 + (p - p0) * w + np.array([0, math.sin(math.pi * w) * 8, 0]); q = q0 + (q - q0) * w
        return p, q

    def cam_smooth(self, t):
        offs = np.linspace(-1.8, 1.8, 13); w = np.exp(-(offs / 0.96) ** 2 / 2); w /= w.sum()
        P = Q = 0
        for o, wi in zip(offs, w):
            p, q = self.cam_raw(t + o); P = P + p * wi; Q = Q + q * wi
        return P, Q

    def _cam_table(self, hz=30, ramp=2.5):
        """Arc-length retiming: constant speed inside each scene, speed eased over `ramp` s at the boundaries,
        and each scene still ends exactly where its path ends (no stop-and-go)."""
        ts = np.arange(0, self.dur + 1 / hz, 1 / hz)
        PQ = np.array([np.concatenate(self.cam_smooth(t)) for t in ts]); P = PQ[:, :3]
        S = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))])
        bounds = [int(round(x * hz)) for x in self.starts] + [len(ts) - 1]
        v = np.zeros(len(ts))
        for i in range(len(self.starts)):
            a, b = bounds[i], bounds[i + 1]
            v[a:b + 1] = (S[b] - S[a]) / max(ts[b] - ts[a], 1e-6)
        k = np.exp(-np.linspace(-2, 2, int(ramp * hz) * 2 + 1) ** 2 * 2); k /= k.sum()
        v = np.convolve(np.pad(v, len(k) // 2, mode="edge"), k, "valid")
        D = np.zeros(len(ts))
        for i in range(len(self.starts)):   # integrate, then rescale per scene so the arc lengths still match
            a, b = bounds[i], bounds[i + 1]
            seg = np.concatenate([[0], np.cumsum(v[a:b] / hz)])
            D[a:b + 1] = S[a] + seg / max(seg[-1], 1e-9) * (S[b] - S[a])
        self._ts, self._PQ, self._S, self._D = ts, PQ, S, D

    def cam(self, t):
        if not hasattr(self, "_D"): self._cam_table()
        d = np.interp(t, self._ts, self._D)
        j = np.clip(np.searchsorted(self._S, d), 1, len(self._S) - 1)
        f = (d - self._S[j - 1]) / max(self._S[j] - self._S[j - 1], 1e-9)
        pq = self._PQ[j - 1] + (self._PQ[j] - self._PQ[j - 1]) * f
        return pq[:3], pq[3:]

    def audio(self, t):
        i = min(int(t * self.fps_b), len(self.aud["bass"]) - 1)
        j = np.searchsorted(self.beats, t) - 1
        beat = self.bstr[j] * math.exp(-(t - self.beats[j]) * 6) if j >= 0 else 0.0
        if 0 <= j < len(self.beats) - 1: chase = j + (t - self.beats[j]) / (self.beats[j + 1] - self.beats[j])
        else: chase = max(j, 0)
        return {k: float(v[i]) for k, v in self.aud.items()} | {"beat": beat, "chase": chase}

    def shock(self, t):
        ev = [x for x in self.starts[1:] + self.accents if 0 <= t - x < 3.5]
        if not ev: return (0.0, 0.0)
        x = max(ev); dt = t - x
        return (math.exp(-dt * 1.1), dt * 26)

    def fade(self, t):
        return min(1.0, t / self.fade_in, max(0.0, (self.dur - t) / self.fade_out))

    # ------------------------------------------------------------ render
    def pack(self, key):
        if key not in self.packs:
            d = np.load(self.pr.p("render", "voxcache", f"{key}.npz"))
            self.packs = {k: v for k, v in list(self.packs.items())[-3:]}
            self.packs[key] = {k: d[k] for k in d.files}
        return self.packs[key]

    def frame(self, t):
        if self.renderer is None:
            from engine.voxel.gl import Renderer
            self.renderer = Renderer(self.W, self.H, self.N, self.R, self.vs)
        a, b, m = self.pair(t)
        for k in (a, b): self.renderer.upload(k, self.pack(k))
        p, q = self.cam(t)
        return self.renderer.render(a, b, m, t, p, q, self.look(t), self.audio(t), fovy=getattr(self.mod, "FOVY", 60.0) if self.H >= self.W else getattr(self.mod, "FOVY_WIDE", 42.0),
                                    fade=self.fade(t), shock=self.shock(t))
