# Contact sheet of rendered stills (render/frame_*.png) to review several frames at once.
#   python engine/contact.py <project> 1.2 5 11 ... [--cols 4] [--width 1600] [--out render/contact.png]
import argparse, os
from PIL import Image, ImageDraw, ImageFont
from common import project_from_argv
pr = project_from_argv()
ap = argparse.ArgumentParser()
ap.add_argument("times", type=float, nargs="+"); ap.add_argument("--cols", type=int, default=4)
ap.add_argument("--width", type=int, default=1600); ap.add_argument("--out", default="render/contact.png")
a = ap.parse_args()
ims = [Image.open(pr.rdir(f"frame_{t:06.2f}.png")).convert("RGB") for t in a.times]
cw = a.width // a.cols; ch = int(cw * ims[0].height / ims[0].width)
rows = (len(ims) + a.cols - 1) // a.cols
sheet = Image.new("RGB", (cw * a.cols, ch * rows), (0, 0, 0))
d = ImageDraw.Draw(sheet)
for i, (t, im) in enumerate(zip(a.times, ims)):
    x, y = i % a.cols * cw, i // a.cols * ch
    sheet.paste(im.resize((cw, ch), Image.LANCZOS), (x, y))
    d.rectangle([x, y, x + 90, y + 28], fill=(0, 0, 0)); d.text((x + 6, y + 6), f"{t:.2f}s", fill=(255, 255, 0))
out = pr.p(a.out); sheet.save(out); print(out)
