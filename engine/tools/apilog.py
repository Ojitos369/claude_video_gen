# Record of every external service call made for a project: projects/<id>/assets/<service>/
#   consulta_N.json   what was sent (url, method, body; never the API key / auth headers)
#   respuesta_N.json  what came back (JSON answer, error, or size of a binary body; base64 blobs replaced by a note)
#   N_<file>          the resource obtained (audio, image…), copied as the service delivered it
# N is per service folder and shared by the three files of one call. Stdlib only.
import json
import os
import re
import shutil
import time

BLOB_KEYS = {"data", "b64_json", "audio", "image", "audioContent"}


def _strip(o):
    """Big base64 payloads are saved as files: keep the JSON readable."""
    if isinstance(o, dict):
        return {k: (f"<base64, {len(v)} caracteres: guardado aparte>" if k in BLOB_KEYS and isinstance(v, str) and len(v) > 1000
                    else _strip(v)) for k, v in o.items()}
    if isinstance(o, list):
        return [_strip(v) for v in o]
    return o


def _dump(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


class Call:
    def __init__(self, proj, service, request):
        self.dir = os.path.join(proj, "assets", service)
        os.makedirs(self.dir, exist_ok=True)
        nums = [int(m.group(1)) for f in os.listdir(self.dir) if (m := re.fullmatch(r"consulta_(\d+)\.json", f))]
        self.n = max(nums, default=0) + 1
        self.t0 = time.time()
        _dump(os.path.join(self.dir, f"consulta_{self.n}.json"), {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), **_strip(request)})

    def response(self, data=None, **extra):
        """data: parsed JSON, bytes (only its size is kept) or text. Can be called again: the last answer wins."""
        if isinstance(data, (bytes, bytearray)):
            data = {"bytes": len(data)}
        _dump(os.path.join(self.dir, f"respuesta_{self.n}.json"),
              {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "seconds": round(time.time() - self.t0, 1), **extra, "body": _strip(data)})

    def file(self, src, name=None):
        dest = os.path.join(self.dir, f"{self.n}_{name or os.path.basename(src)}")
        shutil.copyfile(src, dest)
        return dest


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as p:
        c = Call(p, "demo", {"url": "u", "body": {"inline_data": {"data": "A" * 2000}}})
        c.response({"candidates": [{"data": "B" * 5000}]}, status=200)
        open(os.path.join(p, "x.wav"), "wb").write(b"1")
        assert os.path.basename(c.file(os.path.join(p, "x.wav"))) == "1_x.wav"
        assert Call(p, "demo", {}).n == 2
        r = json.load(open(os.path.join(p, "assets", "demo", "consulta_1.json")))
        assert "guardado aparte" in r["body"]["inline_data"]["data"]
        assert json.load(open(os.path.join(p, "assets", "demo", "respuesta_1.json")))["status"] == 200
        print("ok")
