# Rough line windows WITHOUT Whisper: global forced alignment (torchaudio MMS_FA) of the known lyrics over the whole vocals.
# Use it when the exact lyrics are given (or Whisper fails); then run align.py to refine word by word.
#   python engine/rough_windows.py <project> [--text letra.txt] [--pad 0.6]
#   --text: plain text file (one sung line per row; ``` fences, blank lines and "[...]" tags are ignored)
#           -> writes lyrics/lyrics_src.json; without --text the lines of an existing lyrics_src.json are reused.
#   Fills "win" of every line from the global alignment (+pad on both sides, never past the neighbour lines).
# Latin scripts only (or lines with "rom"): MMS_FA uses a romanised character dictionary.
import argparse, json, os, re, unicodedata
import numpy as np, torch, torchaudio
from common import project_from_argv
pr = project_from_argv()
ap = argparse.ArgumentParser()
ap.add_argument("--text"); ap.add_argument("--lang", default="es"); ap.add_argument("--pad", type=float, default=0.6)
ap.add_argument("--chunk", type=float, default=20.0)
a = ap.parse_args()
src_path = pr.p("lyrics", "lyrics_src.json")
if a.text:
    rows = [r.strip() for r in open(pr.p(a.text) if not os.path.isabs(a.text) else a.text, encoding="utf-8")]
    rows = [r for r in rows if r and not r.startswith("```") and not re.fullmatch(r"\[.*\]", r)]
    SRC = {"language": a.lang, "script": "Latin", "lines": [{"text": r, "es": ""} for r in rows]}
else:
    SRC = json.load(open(src_path, encoding="utf-8"))
lines = SRC["lines"]

dev = "cuda" if torch.cuda.is_available() else "cpu"
bundle = torchaudio.pipelines.MMS_FA
model = bundle.get_model(with_star=False).to(dev).eval()
dic = bundle.get_dict(star=None)
wav, sr = torchaudio.load(pr.vocals)
wav = torchaudio.functional.resample(wav.mean(0, keepdim=True), sr, bundle.sample_rate); sr = bundle.sample_rate

# emissions in chunks (whole-song attention does not fit in VRAM), concatenated
ems, step = [], int(a.chunk * sr)
with torch.inference_mode():
    for i in range(0, wav.shape[1], step):
        seg = wav[:, i:i + step]
        if seg.shape[1] < sr // 10: seg = torch.nn.functional.pad(seg, (0, sr // 10 - seg.shape[1]))
        em, _ = model(seg.to(dev))
        ems.append(em[0].cpu())
em = torch.cat(ems)[None]
fr = wav.shape[1] / sr / em.shape[1]          # seconds per emission frame

def norm(w):
    w = unicodedata.normalize("NFKD", w.lower())
    return "".join(c for c in w if c in dic)

toks, owner = [], []
for li, L in enumerate(lines):
    for w in (L.get("rom") or L["text"]).split():
        t = norm(w)
        if not t: continue
        for c in t: toks.append(dic[c]); owner.append(li)
ali, scores = torchaudio.functional.forced_align(em, torch.tensor([toks]), blank=0)
spans = torchaudio.functional.merge_tokens(ali[0], scores[0].exp())
assert len(spans) == len(toks)
owner = np.array(owner)
for li, L in enumerate(lines):
    idx = np.nonzero(owner == li)[0]
    L["_s"], L["_e"] = spans[idx[0]].start * fr, spans[idx[-1]].end * fr
    L["_score"] = float(np.mean([spans[i].score for i in idx]))
for li, L in enumerate(lines):
    lo = lines[li - 1]["_e"] if li else 0.0
    hi = lines[li + 1]["_s"] if li + 1 < len(lines) else wav.shape[1] / sr
    L["win"] = [round(max(lo, L["_s"] - a.pad, 0.0), 2), round(min(hi, L["_e"] + a.pad), 2)]
    print(f'{L["_s"]:7.2f} {L["_e"]:7.2f}  score {L["_score"]:.2f}  {L["text"]}')
for L in lines:
    for k in ("_s", "_e", "_score"): L.pop(k)
json.dump(SRC, open(src_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("->", src_path)
