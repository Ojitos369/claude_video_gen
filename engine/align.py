# Forced alignment (torchaudio MMS_FA) of lyrics/lyrics_src.json -> lyrics/lyrics.json (+ .srt)
#   python engine/align.py <project>
# lyrics_src.json: {"language": "ko", "script": "Hangul", "lines": [{"win": [a, b], "text": ..., "rom": ..., "es": ...}]}
#   win  = time window (s) where the line is sung (rough, from the transcripts)
#   text = original line; rom = romanization (required for non-Latin scripts, same word count as text); es = Spanish translation
# Edit lyrics_src.json and re-run to fix timing without re-transcribing.
import json, re, unicodedata, torch, torchaudio
from common import project_from_argv
pr = project_from_argv()
SRC = json.load(open(pr.p("lyrics", "lyrics_src.json")))
src = SRC["lines"]
dev = "cuda" if torch.cuda.is_available() else "cpu"
bundle = torchaudio.pipelines.MMS_FA
model = bundle.get_model(with_star=False).to(dev).eval()
dic = bundle.get_dict(star=None)
wav, sr = torchaudio.load(pr.vocals)
wav = torchaudio.functional.resample(wav.mean(0, keepdim=True), sr, bundle.sample_rate); sr = bundle.sample_rate

def norm(w):
    w = unicodedata.normalize("NFKD", w.lower())
    return "".join(c for c in w if c in dic)

# vocal activity (10 ms frames) used to trim word edges to where the voice actually sounds
import numpy as np
v = wav[0].numpy(); hop = sr // 100
rms = np.sqrt(np.convolve(v**2, np.ones(hop*3)/(hop*3), "same")[::hop])
act = rms > max(0.012, 0.08 * np.percentile(rms, 95))
def trim(s, e):
    i, j = int(s*100), int(e*100)
    idx = np.nonzero(act[i:j+1])[0]
    return (s, e) if len(idx) == 0 else ((i+idx[0])/100, (i+idx[-1])/100)

out = []
for L in src:
    a, b = L["win"]
    disp = L["text"].split()
    align_words = (L.get("rom") or L["text"]).split()
    assert len(disp) == len(align_words), L
    toks = [norm(w) or "a" for w in align_words]   # punctuation-only words get a dummy token
    seg = wav[:, int(a*sr):int(b*sr)].to(dev)
    with torch.inference_mode():
        em, _ = model(seg)
    flat = [dic[c] for t in toks for c in t]
    ali, scores = torchaudio.functional.forced_align(em, torch.tensor([flat], device=dev), blank=0)
    spans = torchaudio.functional.merge_tokens(ali[0], scores[0].exp())
    ratio = seg.shape[1] / em.shape[1] / sr
    words, i = [], 0
    for d, t in zip(disp, toks):
        sp = spans[i:i+len(t)]; i += len(t)
        ws, we = trim(a + sp[0].start*ratio, a + sp[-1].end*ratio)
        words.append({"w": d, "s": round(ws, 3), "e": round(we, 3),
                      "score": round(sum(s.score for s in sp)/len(sp), 2)})
    out.append({"start": words[0]["s"], "end": words[-1]["e"], "text": L["text"], "rom": L.get("rom", ""),
                "es": L["es"], "words": words})
    print(f'{words[0]["s"]:7.2f} {words[-1]["e"]:7.2f}  ' + " ".join(f'{w["w"]}({w["score"]})' for w in words))

json.dump({"language": SRC["language"], "script": SRC.get("script", ""), "lines": out}, open(pr.p("lyrics", "lyrics.json"), "w"), ensure_ascii=False, indent=1)
f = lambda t: f"{int(t//3600):02d}:{int(t%3600//60):02d}:{int(t%60):02d},{int(t*1000%1000):03d}"
with open(pr.p("lyrics", "lyrics.srt"), "w") as fh:
    for n, L in enumerate(out, 1):
        fh.write(f'{n}\n{f(L["start"])} --> {f(L["end"])}\n{L["text"]}\n' + (f'{L["rom"]}\n' if L["rom"] else "") + f'{L["es"]}\n\n')

# --- post-pass: snap line starts to nearest vocal onset (<=150 ms), remove overlaps, report ---
import librosa
y, osr = librosa.load(pr.vocals, sr=22050, mono=True)
ons = librosa.onset.onset_detect(y=y, sr=osr, units="time", backtrack=True)
for i, l in enumerate(out):
    o = ons[np.argmin(abs(ons - l["start"]))]
    l["onset_diff"] = round(float(o - l["start"]), 3)
    if abs(o - l["start"]) <= 0.15:
        l["start"] = l["words"][0]["s"] = round(float(o), 3)
for a_, b_ in zip(out, out[1:]):
    if a_["end"] > b_["start"] - 0.02:
        a_["end"] = a_["words"][-1]["e"] = round(b_["start"] - 0.02, 3)
bad = [(round(l["start"], 2), l["onset_diff"], l["text"]) for l in out if abs(l["onset_diff"]) > 0.15]
print("lines without vocal onset within 150 ms:", bad)
json.dump({"language": SRC["language"], "script": SRC.get("script", ""), "lines": out}, open(pr.p("lyrics", "lyrics.json"), "w"), ensure_ascii=False, indent=1)
with open(pr.p("lyrics", "lyrics.srt"), "w") as fh:
    for n, L in enumerate(out, 1):
        fh.write(f'{n}\n{f(L["start"])} --> {f(L["end"])}\n{L["text"]}\n' + (f'{L["rom"]}\n' if L["rom"] else "") + f'{L["es"]}\n\n')
