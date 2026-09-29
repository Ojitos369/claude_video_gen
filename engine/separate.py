# Vocal / instrumental separation with Demucs (GPU if available).
#   python engine/separate.py <project>   -> audio/demucs/htdemucs/<stem>/{vocals,no_vocals}.wav
import subprocess, sys, torch
from common import project_from_argv
pr = project_from_argv()
dev = "cuda" if torch.cuda.is_available() else "cpu"
print("device:", dev)
subprocess.run([sys.executable, "-m", "demucs", "--two-stems=vocals", "-n", "htdemucs", "-d", dev,
                "-o", pr.p("audio", "demucs"), pr.analysis_audio], check=True)
print(pr.vocals)
