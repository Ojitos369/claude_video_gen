# Beat/energy timing shared by the renderer and the scenes. init() is called once per process by render.py.
import math
import numpy as np

FPS = 30
beats = downs = energy = None
down_set = set()

def init(beats_json, fps):
    global beats, downs, energy, down_set, FPS
    FPS = fps
    beats = np.array(beats_json["beats"]); downs = np.array(beats_json["downbeats"])
    down_set = set(np.round(downs, 3))
    energy = np.convolve(np.array(beats_json["energy"]), np.ones(9) / 9, "same")

def snap(t, arr):
    return float(arr[np.argmin(np.abs(arr - t))])

def pulse(t):
    """1 right on a downbeat (0.6 on other beats), decaying in ~110 ms."""
    i = np.searchsorted(beats, t) - 1
    if i < 0: return 0.0
    k = 1.0 if round(beats[i], 3) in down_set else 0.6
    return k * math.exp(-(t - beats[i]) / 0.11)

def since_beat(t):
    i = np.searchsorted(beats, t) - 1
    return (t - beats[i], i) if i >= 0 else (9.0, 0)

def en(t):
    """Smoothed RMS energy 0..1 (sampled at 30 Hz)."""
    return float(energy[min(int(t * 30), len(energy) - 1)])
