# Quick "what is sung here" check without Whisper: greedy CTC decoding of MMS_FA emissions over the vocals (letters only).
#   python engine/ctc_peek.py <project> A B [--step 2]   -> one row of decoded letters every `step` seconds between A and B
import argparse, torch, torchaudio
from common import project_from_argv
pr = project_from_argv()
ap = argparse.ArgumentParser(); ap.add_argument("a", type=float); ap.add_argument("b", type=float); ap.add_argument("--step", type=float, default=2.0)
a = ap.parse_args()
bundle = torchaudio.pipelines.MMS_FA
dev = "cuda" if torch.cuda.is_available() else "cpu"
model = bundle.get_model(with_star=False).to(dev).eval()
labels = bundle.get_labels(star=None)
wav, sr = torchaudio.load(pr.vocals)
wav = torchaudio.functional.resample(wav.mean(0, keepdim=True), sr, bundle.sample_rate); sr = bundle.sample_rate
seg = wav[:, int(a.a * sr):int(a.b * sr)].to(dev)
with torch.inference_mode(): em, _ = model(seg)
ids = em[0].argmax(-1).tolist(); fr = seg.shape[1] / sr / len(ids)
rows, prev = {}, None
for i, k in enumerate(ids):
    if k != prev and k != 0:
        rows.setdefault(int(i * fr // a.step), []).append(labels[k])
    prev = k
for r in sorted(rows): print(f"{a.a + r * a.step:7.1f}  {''.join(rows[r]).replace('|', ' ')}")
