# Create a new video project from an audio file.
#   python engine/new_project.py <name> <path/to/audio>
import json, os, shutil, sys
from common import ROOT
if len(sys.argv) != 3: sys.exit("usage: python engine/new_project.py <name> <audio file>")
name, audio = sys.argv[1], sys.argv[2]
d = os.path.join(ROOT, "projects", name)
if os.path.exists(d): sys.exit(f"already exists: {d}")
for sub in ("audio", "lyrics", "render", "out"): os.makedirs(os.path.join(d, sub))
shutil.copy2(audio, d)
base = os.path.basename(audio)
json.dump({"audio": base, "output": f"{name}.mp4", "lyrics_mode": "auto", "font_index": 1},
          open(os.path.join(d, "config.json"), "w"), indent=1)
json.dump({"_doc": "sections: kind = intro|verse|pre|chorus|outro (text style + transition strength). "
                   "blocks: motif per lyric passage, start in s (snapped to a beat); optional cut_every (default 2.0 s).",
           "sections": [{"start": 0.0, "name": "intro", "kind": "intro"}],
           "blocks": [{"start": 0.0, "motif": "dream", "about": ""}]}, open(os.path.join(d, "storyboard.json"), "w"), indent=1)
tpl = open(os.path.join(ROOT, "engine", "templates", "prompt.md")).read()
open(os.path.join(d, "prompt.md"), "w").write(tpl.replace("{name}", name).replace("{audio}", base))
open(os.path.join(d, "PROGRESO.md"), "w").write(f"# PROGRESO — {name}\n\n## Pasos\n- [ ] 1. Separación de voz\n")
print(f"created {d}\nnext: edit projects/{name}/prompt.md (section 'Instrucciones propias') and ask Claude to run it")
