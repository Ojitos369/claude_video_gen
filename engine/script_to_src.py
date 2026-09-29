# Narrated stories: build lyrics/lyrics_src.json from the exact script instead of the Whisper text.
#   python engine/script_to_src.py <project> historia.md [--max-words 8]
# Splits every paragraph into short caption lines (sentences, then commas / even split), and finds each line's time
# window by matching script words to the Whisper words of lyrics/raw_transcript.json (difflib). Each line keeps
# "para" (paragraph index) so the story timeline can group paragraphs into parts. Then run engine/align.py.
import argparse, difflib, json, re, unicodedata
from common import project_from_argv
pr = project_from_argv()
ap = argparse.ArgumentParser(); ap.add_argument("script"); ap.add_argument("--max-words", type=int, default=8)
a = ap.parse_args()

def norm(w):
    w = unicodedata.normalize("NFKD", w.lower())
    return "".join(c for c in w if "a" <= c <= "z" or c.isdigit())

STOP = set("a al de del la las el los lo le les y e o u que en su sus se con por para un una unos unas mi tu no ni como".split())

def split_line(words, maxw):
    if len(words) <= maxw: return [words]
    cuts = [i + 1 for i, w in enumerate(words[:-1]) if re.search(r"[,;:]$|—$", w) and 2 <= i + 1 <= len(words) - 2]
    if cuts:
        mid = min(cuts, key=lambda c: abs(c - len(words) / 2))
        return split_line(words[:mid], maxw) + split_line(words[mid:], maxw)
    n = -(-len(words) // maxw); k = -(-len(words) // n)
    # even split, nudged so a line never ends on a short function word ("a las / altas temperaturas")
    cut = min((c for c in range(max(2, k - 2), min(len(words) - 1, k + 3)) if norm(words[c - 1]) not in STOP),
              key=lambda c: abs(c - k), default=k)
    return split_line(words[:cut], maxw) + split_line(words[cut:], maxw)

paras = [p.strip() for p in open(pr.p(a.script)).read().split("\n\n") if p.strip()]
lines = []
for pi, p in enumerate(paras):
    for sent in re.split(r"(?<=[.?!…])\s+(?=[—¿¡A-ZÁÉÍÓÚÑ])", p):
        for chunk in split_line(sent.split(), a.max_words):
            lines.append({"para": pi, "text": " ".join(chunk)})

tw = [w for s in json.load(open(pr.p("lyrics", "raw_transcript.json")))["segments"] for w in s["words"]]
sw = [(li, norm(w)) for li, l in enumerate(lines) for w in l["text"].split()]
sm = difflib.SequenceMatcher(None, [x[1] for x in sw], [norm(w["w"]) for w in tw], autojunk=False)
match = {}
for blk in sm.get_matching_blocks():
    for k in range(blk.size): match[blk.a + k] = blk.b + k
print(f"matched {len(match)}/{len(sw)} script words")
pos = 0
for li, l in enumerate(lines):
    idx = [i for i in range(pos, pos + len(l["text"].split()))]; pos += len(idx)
    m = [match[i] for i in idx if i in match]
    if not m:   # no match: between neighbours
        before = [match[i] for i in range(idx[0]) if i in match]; after = [match[i] for i in range(idx[-1] + 1, len(sw)) if i in match]
        s = tw[before[-1]]["e"] if before else 0.0; e = tw[after[0]]["s"] if after else tw[-1]["e"]
    else:
        s, e = tw[m[0]]["s"], tw[m[-1]]["e"]
        miss_head = sum(1 for i in idx if i not in match and i < min(k for k in idx if k in match))
        miss_tail = sum(1 for i in idx if i not in match and i > max(k for k in idx if k in match))
        s -= 0.35 * miss_head; e += 0.35 * miss_tail
    l["win"] = [round(max(0, s - 0.4), 2), round(e + 0.4, 2)]
    if len(m) < 0.5 * len(idx):
        print(f"WARNING line {li} mostly not heard in the narration ({len(m)}/{len(idx)} words): {l['text']!r} -> check the audio, edit lyrics_src.json")
    l["es"] = ""
json.dump({"language": "es", "script": "Latin", "lines": [{"win": l["win"], "text": l["text"], "es": "", "para": l["para"]} for l in lines]},
          open(pr.p("lyrics", "lyrics_src.json"), "w"), ensure_ascii=False, indent=1)
print(len(paras), "paragraphs,", len(lines), "lines")
