# Narrated stories: insert breathing pauses between story parts and build the soundtrack.
#   python engine/story_timeline.py <project>
# config.json "story": {"script", "parts": [paragraph index that starts each part], "pause", "intro", "outro",
#                       "music_gain_db", "duck_db", "crossfade"} and top-level "voice", "music".
# Reads lyrics/lyrics.json (narration time, from align.py) and writes:
#   lyrics/lyrics_narration.json (untouched copy), lyrics/lyrics.json (timeline time, with "para" per line),
#   audio/voice_timeline.wav, audio/music_bed.wav (looped music, for beats.py), audio/mix.wav (voice + ducked music),
#   audio/timeline.json {duration, pauses: [{start, end}], parts: [{start, end, paras}]}
import json, os, numpy as np, soundfile as sf, librosa
from common import project_from_argv
pr = project_from_argv()
S = pr.cfg["story"]; SR = 48000
lyr_p, narr_p = pr.p("lyrics", "lyrics.json"), pr.p("lyrics", "lyrics_narration.json")
lyr = json.load(open(lyr_p))
if lyr.get("timeline"): lyr = json.load(open(narr_p))          # re-run: start from narration times
else: json.dump(lyr, open(narr_p, "w"), ensure_ascii=False, indent=1)
src = json.load(open(pr.p("lyrics", "lyrics_src.json")))["lines"]
lines = lyr["lines"]
for l, s in zip(lines, src): l["para"] = s["para"]

voice, _ = librosa.load(pr.vocals, sr=SR, mono=True)
voice = voice / (np.abs(voice).max() + 1e-9) * 0.89
parts = S["parts"]
# cut points (narration time) between the last line of a part and the first line of the next
cuts = []
for p0 in parts[1:]:
    i = next(k for k, l in enumerate(lines) if l["para"] >= p0)
    cuts.append((lines[i - 1]["end"] + lines[i]["start"]) / 2)
P, intro = S["pause"], S["intro"]
shift = lambda t: t + intro + P * sum(1 for c in cuts if t > c)
pieces, prev = [np.zeros(int(intro * SR))], 0
for c in cuts:
    pieces += [voice[int(prev * SR):int(c * SR)], np.zeros(int(P * SR))]; prev = c
pieces += [voice[int(prev * SR):], np.zeros(int(S["outro"] * SR))]
vt = np.concatenate(pieces); N = len(vt); dur = N / SR
for l in lines:
    l["start"], l["end"] = round(shift(l["start"]), 3), round(shift(l["end"]), 3)
    for w in l["words"]: w["s"], w["e"] = round(shift(w["s"]), 3), round(shift(w["e"]), 3)
json.dump({**lyr, "timeline": True, "lines": lines}, open(lyr_p, "w"), ensure_ascii=False, indent=1)

# music bed: loop with crossfade, fade in/out
m, _ = librosa.load(pr.p(pr.cfg["music"]), sr=SR, mono=False)
m = np.atleast_2d(m); xf = int(S["crossfade"] * SR)
bed = m.copy()
while bed.shape[1] < N:
    ramp = np.linspace(0, 1, xf)
    bed = np.concatenate([bed[:, :-xf], bed[:, -xf:] * (1 - ramp) + m[:, :xf] * ramp, m[:, xf:]], axis=1)
bed = bed[:, :N] * 10 ** (S["music_gain_db"] / 20)
bed[:, :SR] *= np.linspace(0, 1, SR); bed[:, -int(S["outro"] * SR):] *= np.linspace(1, 0, int(S["outro"] * SR))
if bed.shape[0] == 1: bed = np.repeat(bed, 2, 0)
# ducking: smoothed voice envelope (fast attack, slow release)
hop = SR // 100
env = np.sqrt(np.convolve(vt ** 2, np.ones(hop * 3) / (hop * 3), "same")[::hop])
act = (env > 0.02).astype(float)
sm = np.zeros_like(act)
for i in range(1, len(act)):
    k = 0.5 if act[i] > sm[i - 1] else 0.03
    sm[i] = sm[i - 1] + (act[i] - sm[i - 1]) * k
gain = 10 ** (S["duck_db"] * np.interp(np.arange(N) / hop, np.arange(len(sm)), sm) / 20)
mix = bed * gain + vt
# loudness: bring speech to target RMS (story.target_db, default -19 dBFS), soft-limit the peaks
speech = mix[:, np.repeat(act, hop)[:N] > 0] if act.any() else mix
g = 10 ** ((S.get("target_db", -19) - 20 * np.log10(np.sqrt((speech ** 2).mean()) + 1e-9)) / 20)
mix = np.tanh(mix * g / 0.97) * 0.97
sf.write(pr.p("audio", "voice_timeline.wav"), vt, SR)
sf.write(pr.p("audio", "music_bed.wav"), bed.T, SR)
sf.write(pr.p("audio", "mix.wav"), mix.T, SR, subtype="PCM_16")
pauses = [{"start": round(c + intro + P * i, 3), "end": round(c + intro + P * (i + 1), 3)} for i, c in enumerate(cuts)]
bounds = [0.0] + [p["end"] for p in pauses] + [dur]
tl = {"duration": dur, "pauses": pauses,
      "parts": [{"start": bounds[i], "end": (pauses[i]["start"] if i < len(pauses) else dur), "paras": parts[i]} for i in range(len(parts))]}
json.dump(tl, open(pr.p("audio", "timeline.json"), "w"), indent=1)
print(f"duration {dur:.2f}s, {len(pauses)} pauses:", [(p['start'], p['end']) for p in pauses])
