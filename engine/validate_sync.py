#   python engine/validate_sync.py <project>
# Cross-check aligned line starts/ends against independent Whisper word timestamps (all passes)
import json, glob
from common import project_from_argv
pr = project_from_argv()
W = []
for f in glob.glob(pr.p("lyrics", "raw_transcript*.json")):
    d = json.load(open(f)); segs = d["segments"] if isinstance(d, dict) else d
    W += [(w["s"], w["e"], w["w"]) for s in segs for w in s["words"]]
L = json.load(open(pr.p("lyrics", "lyrics.json")))["lines"]
for i, l in enumerate(L):
    ds = min(W, key=lambda w: abs(w[0]-l["start"]))
    de = min(W, key=lambda w: abs(w[1]-l["end"]))
    flag = "  <-- revisar" if abs(ds[0]-l["start"]) > 0.15 else ""
    print(f'{i:2d} {l["start"]:7.2f} (whisper {ds[0]:7.2f} {ds[2]}) end {l["end"]:7.2f} (whisper {de[1]:7.2f}) {l["text"][:20]}{flag}')
    if i and L[i-1]["end"] > l["start"]: print("   overlap with previous")
