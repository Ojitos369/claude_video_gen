# Whisper transcription of the separated vocals with word timestamps.
#   python engine/transcribe.py <project>                     full pass with VAD, auto language -> lyrics/raw_transcript.json
#   python engine/transcribe.py <project> --windows A B [--lang ko] [--win 10 --hop 5]
#        extra pass over fixed windows without VAD (recovers lines the full pass merged or skipped)
#        -> lyrics/raw_transcript_A_B.json
# Whisper hallucinates in instrumentals ("thanks for watching"...): always review before writing lyrics_src.json.
import argparse, json, os, sys
from common import project_from_argv, cuda_lib_path
pr = project_from_argv()
if "LD_LIBRARY_PATH" not in os.environ or "cublas" not in os.environ["LD_LIBRARY_PATH"]:
    os.environ["LD_LIBRARY_PATH"] = cuda_lib_path() + ":" + os.environ.get("LD_LIBRARY_PATH", "")
    os.execv(sys.executable, [sys.executable] + [sys.argv[0], pr.dir] + sys.argv[1:])   # ctranslate2 reads it at load time
ap = argparse.ArgumentParser()
ap.add_argument("--windows", nargs=2, type=float)
ap.add_argument("--lang")
ap.add_argument("--win", type=float, default=10); ap.add_argument("--hop", type=float, default=5)
a = ap.parse_args()

import numpy as np, soundfile as sf, librosa, torch
from faster_whisper import WhisperModel
dev = "cuda" if torch.cuda.is_available() else "cpu"
m = WhisperModel(pr.cfg["whisper_model"], device=dev, compute_type="float16" if dev == "cuda" else "int8")
W = lambda w, off: {"w": w.word.strip(), "s": round(w.start + off, 3), "e": round(w.end + off, 3), "p": round(w.probability, 2)}

if not a.windows:
    segs, info = m.transcribe(pr.vocals, language=a.lang, word_timestamps=True, vad_filter=True, beam_size=5, condition_on_previous_text=False)
    out = {"language": info.language, "prob": info.language_probability, "segments": []}
    for s in segs:
        out["segments"].append({"start": s.start, "end": s.end, "text": s.text.strip(), "words": [W(w, 0) for w in s.words]})
        print(f"{s.start:7.2f} {s.end:7.2f} {s.text}")
    json.dump(out, open(pr.p("lyrics", "raw_transcript.json"), "w"), ensure_ascii=False, indent=1)
    print("language:", info.language, round(info.language_probability, 3))
else:
    y, sr = sf.read(pr.vocals)
    y = librosa.resample(y.mean(1).astype(np.float32) if y.ndim > 1 else y.astype(np.float32), orig_sr=sr, target_sr=16000)
    lang = a.lang or json.load(open(pr.p("lyrics", "raw_transcript.json")))["language"]
    t0, (ta, tb) = a.windows[0], a.windows
    out = []
    while t0 < tb:
        segs, _ = m.transcribe(y[int(t0 * 16000):int((t0 + a.win) * 16000)], language=lang, word_timestamps=True,
                               vad_filter=False, beam_size=5, condition_on_previous_text=False)
        for s in segs:
            print(f"[{t0:6.1f}] {s.start + t0:7.2f} {s.end + t0:7.2f} {s.text}")
            out.append({"win": t0, "start": s.start + t0, "end": s.end + t0, "text": s.text.strip(), "words": [W(w, t0) for w in s.words]})
        t0 += a.hop
    json.dump(out, open(pr.p("lyrics", f"raw_transcript_{int(ta)}_{int(tb)}.json"), "w"), ensure_ascii=False, indent=1)
