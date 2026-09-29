# Tempo, beats, downbeats, sections, energy -> audio/beats.json
#   python engine/beats.py <project>
# section_bounds_auto is only a hint: final sections are written by hand in storyboard.json.
import json, numpy as np, librosa
from common import project_from_argv
pr = project_from_argv()
y, sr = librosa.load(pr.p(pr.cfg["beats_audio"]) if pr.cfg["beats_audio"] else pr.analysis_audio, sr=22050, mono=True)
dur = len(y) / sr
tempo, beats = librosa.beat.beat_track(y=y, sr=sr, units="time", tightness=120)
tempo = float(np.atleast_1d(tempo)[0])
# downbeats: pick the beat phase (of 4) with the strongest low-frequency onset
S = np.abs(librosa.stft(y)); low = librosa.onset.onset_strength(S=librosa.amplitude_to_db(S[:40]), sr=sr)
lt = librosa.times_like(low, sr=sr)
bstr = np.interp(beats, lt, low)
phase = int(np.argmax([bstr[p::4].mean() for p in range(4)]))
down = beats[phase::4]
# energy curve (RMS, 30 fps) normalised
rms = librosa.feature.rms(y=y, hop_length=735)[0]; rms = rms / rms.max()
# sections: agglomerative segmentation on beat-synced chroma+mfcc, snapped to downbeats
C = librosa.feature.chroma_cqt(y=y, sr=sr); M = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
F = librosa.util.sync(np.vstack([librosa.util.normalize(C), librosa.util.normalize(M)]), librosa.time_to_frames(beats, sr=sr))
bounds = librosa.segment.agglomerative(F, 10)
bt = [0.0] + sorted(set(float(down[np.argmin(abs(down - beats[min(b, len(beats)-1)]))]) for b in bounds if b > 0)) + [dur]
# band energies at 60 fps (bass 20-160, lowmid 160-1200, highmid 1200-5000, high 5000-11000 Hz), onset, rms;
# log scale + percentile normalisation (3 / 99.3) so one peak does not flatten the rest
hop60 = sr // 60
S60 = np.abs(librosa.stft(y, n_fft=2048, hop_length=hop60)); f60 = librosa.fft_frequencies(sr=sr, n_fft=2048)
n60 = int(np.ceil(dur * 60))
def nrm(x, log=True):
    x = np.log1p(x * 20) if log else x
    lo, hi = np.percentile(x, 3), np.percentile(x, 99.3)
    return np.pad(np.clip((x - lo) / (hi - lo + 1e-9), 0, 1), (0, max(0, n60 - len(x))))[:n60]
bands = {k: nrm(S60[(f60 >= a) & (f60 < b)].mean(0)) for k, (a, b) in
         {"bass": (20, 160), "lowmid": (160, 1200), "highmid": (1200, 5000), "high": (5000, 11000)}.items()}
bands["onset"] = nrm(librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop60), False)
bands["rms"] = nrm(librosa.feature.rms(y=y, frame_length=2048, hop_length=hop60)[0], False)
ons = librosa.onset.onset_strength(y=y, sr=sr)
bstr = np.interp(librosa.time_to_frames(beats, sr=sr), np.arange(len(ons)), ons)
bstr = np.clip(bstr / np.percentile(bstr, 95), 0, 1)
json.dump({"duration": dur, "tempo": tempo, "beats": [round(float(b), 3) for b in beats],
           "beat_strength": [round(float(x), 2) for x in bstr],
           "downbeats": [round(float(b), 3) for b in down], "section_bounds_auto": [round(b, 2) for b in bt],
           "energy_fps": 30, "energy": [round(float(v), 3) for v in rms],
           "bands_fps": 60, "bands": {k: [int(round(v * 255)) for v in x] for k, x in bands.items()}},
          open(pr.p("audio", "beats.json"), "w"), indent=0)
print("tempo", tempo, "beats", len(beats), "first", beats[:6], "phase", phase)
print("auto sections", [round(b, 1) for b in bt])
print("energy per 4s", [round(float(rms[int(t*30)]), 2) for t in range(0, int(dur), 4)])
