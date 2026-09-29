# Project loading: every engine script takes a project name (projects/<name>) or a path as first argument.
import json, os, sys

ENGINE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(ENGINE)
sys.path.insert(0, ROOT)          # so `engine.*` imports work when scripts run directly

DEFAULTS = {
    "audio": None,                 # audio file inside the project folder (default: first .mp3/.wav/.flac/.m4a found)
    "output": None,                # final file name in out/ (default: <project>.mp4)
    # Output format. Priority: explicit width+height > "aspect" > aspect of the background video > 9:16.
    "aspect": None,                # e.g. "9:16", "16:9", "1:1", "4:5"
    "long_side": 1920,             # pixels of the longest side when the size is derived
    "width": None, "height": None,
    "fps": None,                   # number, "24000/1001" or "source"; default: background video fps, else 30
    "lyrics_mode": "auto",         # auto | orig | orig+es | orig+rom+es  (auto: es->orig, en->orig+es, others->orig+rom+es)
    "font_bold": "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "font_regular": "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "font_index": 1,               # face inside .ttc (NotoSansCJK: 0 JP, 1 KR, 2 SC, 3 TC)
    "text_colors": {"unsung": [255, 255, 255], "sung": [255, 150, 205], "glow": [255, 70, 160],
                    "rom": [205, 190, 255], "tr": [255, 236, 214], "outline": [30, 10, 45], "panel": [18, 6, 32, 120]},
    "palette": {},                 # overrides named scene colors, e.g. {"rose": [255, 90, 160]}
    "fade_out": 4.0,               # seconds of fade to black before the end (0 = off)
    "background": {"type": "scenes"},   # or {"type": "video", "source": "clip.mp4", "dim": 0.55}: source video under a black cover, no scenes
    "text_pulse": True,            # lyrics scale slightly on beats
    "text_size": 92,               # main text size (px at 1080 wide); translation lines scale with it
    "caption_position": "center",  # center | bottom (lower third, e.g. subtitles for narration)
    "voice": None,                 # separate clean voice/narration file: used instead of Demucs vocals for transcription/alignment
    "beats_audio": None,           # file analysed by beats.py (default: the project audio), e.g. a music bed
    "scene_canvas": None,          # [w, h] design canvas of scenes (default [540, 960]); use [540, 540] for 1:1 projects
    "segment_seconds": 10, "jobs": None,          # None: machine.render_jobs from settings.local.json
    "nvenc_cq": 19, "audio_bitrate": "320k",
    "whisper_model": "large-v3",
}

class Project:
    def __init__(self, arg, aspect=None):
        d = arg if os.path.isdir(arg) else os.path.join(ROOT, "projects", arg)
        if not os.path.isdir(d): sys.exit(f"project not found: {arg}")
        self.dir, self.name = os.path.abspath(d), os.path.basename(os.path.abspath(d))
        cfg_path = self.p("config.json")
        user = json.load(open(cfg_path)) if os.path.exists(cfg_path) else {}
        self.cfg = {**DEFAULTS, **user, "text_colors": {**DEFAULTS["text_colors"], **user.get("text_colors", {})}}
        if not self.cfg["audio"]:
            aud = sorted(f for f in os.listdir(d) if f.lower().endswith((".mp3", ".wav", ".flac", ".m4a", ".ogg", ".mp4", ".mkv", ".mov", ".webm")))
            if not aud: sys.exit("no audio file in project folder")
            self.cfg["audio"] = aud[0]
        self.stem = os.path.splitext(self.cfg["audio"])[0]
        self.machine = machine_info()
        if not self.cfg["jobs"]:
            self.cfg["jobs"] = self.machine.get("render_jobs") or max(1, (os.cpu_count() or 2) // 3)
        self.variant = ""
        if aspect:
            self.cfg.update(aspect=aspect, width=None, height=None); self.variant = aspect.replace(":", "x")
        self._resolve_format()
        for sub in ("audio", "lyrics", "render", "out"): os.makedirs(self.p(sub), exist_ok=True)

    def p(self, *a): return os.path.join(self.dir, *a)

    def _resolve_format(self):
        from fractions import Fraction
        c, bg = self.cfg, self.cfg["background"]
        src = probe_video(self.p(bg["source"])) if bg.get("type") == "video" else None
        if not (c["width"] and c["height"]):
            if c["aspect"]: aw, ah = map(float, str(c["aspect"]).split(":"))
            elif src: aw, ah = src["width"], src["height"]
            else: aw, ah = 9, 16
            k = c["long_side"] / max(aw, ah)
            c["width"], c["height"] = int(round(aw * k / 2)) * 2, int(round(ah * k / 2)) * 2
        fps = c["fps"] or ("source" if src else 30)
        if fps == "source": fps = src["fps"] if src else 30
        c["fps"] = Fraction(str(fps)).limit_denominator(1001)
    @property
    def audio(self): return self.p(self.cfg["audio"])
    @property
    def analysis_audio(self):
        """WAV/MP3 used for separation and beat analysis; audio is extracted once if the source is a video file."""
        if self.cfg["audio"].lower().endswith((".mp3", ".wav", ".flac", ".m4a", ".ogg")): return self.audio
        wav = self.p("audio", self.stem + "_audio.wav")
        if not os.path.exists(wav):
            import subprocess
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", self.audio, "-vn", "-ac", "2", wav], check=True)
        return wav
    @property
    def vocals(self):
        if self.cfg["voice"]: return self.p(self.cfg["voice"])
        return self._demucs_vocals
    @property
    def _demucs_vocals(self): return self.p("audio", "demucs", "htdemucs", os.path.splitext(os.path.basename(self.analysis_audio))[0], "vocals.wav")
    def rdir(self, *a):
        """Render working folder (per format variant)."""
        d = self.p("render", self.variant) if self.variant else self.p("render")
        os.makedirs(d, exist_ok=True); return os.path.join(d, *a)
    def out_name(self, name):
        b, e = os.path.splitext(name); return self.p("out", f"{b}_{self.variant}{e}" if self.variant else name)
    @property
    def output(self): return self.out_name(self.cfg["output"] or f"{self.name}.mp4")

def machine_info():
    """Host details from settings.local.json (detected when the service starts; detected here if missing)."""
    try:
        from engine.tools import local_settings, machine
        return local_settings.load().get("machine") or machine.ensure()[0]
    except Exception:
        return {}

def video_encoder_args(machine, cq):
    """ffmpeg args for the best working H.264 encoder of this machine (NVENC > QSV > AMF > VideoToolbox > x264)."""
    enc = (machine or {}).get("video_encoder") or "libx264"
    if enc == "h264_nvenc": return ["-c:v", enc, "-preset", "p6", "-rc", "vbr", "-cq", str(cq), "-b:v", "0", "-profile:v", "high"]
    if enc == "h264_qsv": return ["-c:v", enc, "-global_quality", str(cq), "-preset", "slow"]
    if enc == "h264_amf": return ["-c:v", enc, "-rc", "cqp", "-qp_i", str(cq), "-qp_p", str(cq), "-quality", "quality"]
    if enc == "h264_videotoolbox": return ["-c:v", enc, "-q:v", "65"]
    return ["-c:v", "libx264", "-preset", "medium", "-crf", str(max(16, cq - 1))]

def probe_video(path):
    import subprocess
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,r_frame_rate",
                          "-of", "json", path], capture_output=True, text=True, check=True).stdout
    st = json.loads(out)["streams"][0]
    return {"width": st["width"], "height": st["height"], "fps": st["r_frame_rate"]}

def audio_codec(path):
    import subprocess
    return subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_name", "-of", "csv=p=0", path],
                          capture_output=True, text=True).stdout.strip()

def project_from_argv():
    """First argument = project. `--aspect 16:9` (any script) renders an alternative format of the same project:
    own render/<16x9>/ folder and out/<name>_16x9.mp4, so the default version is not overwritten."""
    if len(sys.argv) < 2 or sys.argv[1].startswith("-"): sys.exit(f"usage: python {os.path.relpath(sys.argv[0])} <project> [options]")
    aspect = None
    if "--aspect" in sys.argv:
        i = sys.argv.index("--aspect"); aspect = sys.argv[i + 1]; del sys.argv[i:i + 2]
    return Project(sys.argv.pop(1), aspect)

def cuda_lib_path():
    """LD_LIBRARY_PATH entries for cuBLAS/cuDNN wheels (needed by faster-whisper/ctranslate2)."""
    import nvidia.cublas.lib, nvidia.cudnn.lib
    return ":".join(os.path.dirname(m.__file__) for m in (nvidia.cublas.lib, nvidia.cudnn.lib))
