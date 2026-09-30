# Music generation tool for video projects (background beds, jingles, full songs with lyrics). Provider / model from
# settings.local.json -> music; key from -> providers.musicful.
#   python engine/tools/gen_music.py <project> --style "lofi calmado, piano, 80 bpm" --out audio/music.wav [--instrumental]
#   python engine/tools/gen_music.py <project> --style "pop alegre" --lyrics-file letra.txt --title "Mi canción" --out audio/song.wav
#   python engine/tools/gen_music.py --info        # remaining songs of the API key
# Musicful (https://docs.musicful.ai/api-reference/): POST /v1/music/generate returns task ids; GET /v1/music/tasks?ids=… until
# each song has an audio_url. Every call usually yields 2 variations: the first goes to --out, the rest to <out>_2, <out>_3…
# Task ids are logged in projects/<id>/audio/music.json before polling: re-running the same command resumes the pending
# task instead of paying for a new song. Songs count against music.max_per_project.
# Every request / answer / downloaded song is also kept in projects/<id>/assets/musicful/ (engine/tools/apilog.py).
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from engine.tools import local_settings  # noqa: E402
from engine.tools.apilog import Call  # noqa: E402

API = "https://api.musicful.ai"
DEFAULT_MODEL = "MFV2.0"


def call(method, path, key, body=None, timeout=120, rec=None):
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", "x-api-key": key, "User-Agent": "video-studio"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read() or b"null")
            if rec: rec.response(d, status=r.status)
            return d
    except urllib.error.HTTPError as e:
        err = e.read().decode(errors="replace")
        if rec: rec.response(err, status=e.code)
        raise SystemExit(f"error {e.code} de Musicful: {err[:800]}")


def unwrap(d):
    """Musicful wraps some answers in {code, msg, data}; fail on a non-OK code."""
    if isinstance(d, dict) and "code" in d and d["code"] not in (0, 200, "0", "200"):
        raise SystemExit(f"Musicful respondió {d.get('code')}: {d.get('msg') or d.get('message') or json.dumps(d)[:400]}")
    return d.get("data", d) if isinstance(d, dict) and "data" in d else d


def task_ids(d):
    """The generate answer is not documented: accept a list of ids, {ids|task_ids: [...]}, or a list of songs."""
    d = unwrap(d)
    if isinstance(d, dict):
        for k in ("ids", "task_ids", "taskIds", "songs", "tasks", "id", "task_id"):
            if d.get(k) is not None: return task_ids(d[k])
    if isinstance(d, (str, int)): return [str(x).strip() for x in str(d).split(",") if str(x).strip()]
    if isinstance(d, list): return [str(x.get("id") or x.get("task_id")) if isinstance(x, dict) else str(x) for x in d]
    raise SystemExit(f"no encontré ids de tarea en la respuesta: {json.dumps(d)[:600]}")


def poll(key, ids, timeout, rec):
    """Wait until every song has an audio_url with a duration (status codes are not documented), or one fails.
    rec keeps the last answer of the task query."""
    t0, last = time.time(), None
    while True:
        songs = unwrap(call("GET", f"/v1/music/tasks?ids={','.join(ids)}", key, rec=rec))
        songs = songs if isinstance(songs, list) else [songs]
        for s in songs:
            if s.get("fail_code") or s.get("fail_reason"):
                raise SystemExit(f"Musicful falló en {s.get('id')}: {s.get('fail_code')} {s.get('fail_reason')}")
        state = [(s.get("id"), s.get("status"), bool(s.get("audio_url")), s.get("duration")) for s in songs]
        if state != last: print("estado:", state, flush=True); last = state
        if songs and all(s.get("audio_url") and (s.get("duration") or 0) > 0 for s in songs):
            return songs
        if time.time() - t0 > timeout:
            raise SystemExit(f"la canción sigue en proceso tras {timeout} s; vuelve a ejecutar el mismo comando para retomarla")
        time.sleep(8)


def save_audio(url, out, rec):
    """Download (the original file is kept in the service record) and, if --out is not the same format, convert with
    ffmpeg (WAV 44.1 kHz stereo for the mixer)."""
    ext = os.path.splitext(url.split("?")[0])[1] or ".mp3"
    tmp = out + ".part" + ext
    urllib.request.urlretrieve(url, tmp)
    rec.file(tmp, os.path.splitext(os.path.basename(out))[0] + ext)
    if os.path.splitext(out)[1].lower() == ext.lower():
        os.replace(tmp, out); return
    subprocess.run([shutil.which("ffmpeg") or "ffmpeg", "-y", "-loglevel", "error", "-i", tmp, "-ar", "44100", "-ac", "2", out], check=True)
    os.remove(tmp)


def variant(out, i):
    base, ext = os.path.splitext(out)
    return out if i == 0 else f"{base}_{i + 1}{ext}"


def main():
    ap = argparse.ArgumentParser(description="Genera música (Musicful) para un proyecto de video")
    ap.add_argument("project", nargs="?"); ap.add_argument("--out", help="ruta dentro del proyecto, p. ej. audio/music.wav")
    ap.add_argument("--style", help="género, ánimo, instrumentos, tempo… (en inglés suele funcionar mejor)")
    ap.add_argument("--lyrics"); ap.add_argument("--lyrics-file"); ap.add_argument("--title", default="")
    ap.add_argument("--instrumental", action="store_true", help="sin voz (fondo para narraciones)")
    ap.add_argument("--gender", choices=["male", "female"], help="voz del cantante")
    ap.add_argument("--model", help="MFV3.0, MFV2.0 (default), MFV1.5X, MFV1.5, MFV1.0")
    ap.add_argument("--timeout", type=int, default=540, help="segundos de espera (la app limita cada comando a 10 min)")
    ap.add_argument("--info", action="store_true", help="muestra las canciones restantes de la API key")
    a = ap.parse_args()
    s = local_settings.load(); cfg = s["music"]
    key = local_settings.key("musicful")
    if not key: raise SystemExit("Falta la API key de Musicful (ajustes de la app -> Plataformas)")
    if a.info:
        d = unwrap(call("GET", "/v1/get_api_key_info", key))
        print(f"canciones restantes: {d.get('key_music_counts')} (estado de la clave {d.get('key_status')})"); return
    if not (a.project and a.out and a.style): ap.error("faltan project, --style y --out")
    if cfg["provider"] != "musicful": raise SystemExit("La generación de música no está configurada (ajustes de la app -> Música)")
    proj = a.project if os.path.isdir(a.project) else os.path.join(local_settings.ROOT, "projects", a.project)
    if not os.path.isdir(proj): raise SystemExit(f"no existe el proyecto {a.project}")
    out = os.path.join(proj, a.out) if not os.path.isabs(a.out) else a.out
    os.makedirs(os.path.dirname(out), exist_ok=True)
    lyrics = a.lyrics or (open(os.path.join(proj, a.lyrics_file) if not os.path.isabs(a.lyrics_file) else a.lyrics_file,
                               encoding="utf-8").read() if a.lyrics_file else "")
    rel = os.path.relpath(out, proj)
    log_path = os.path.join(proj, "audio", "music.json")
    log = json.load(open(log_path, encoding="utf-8")) if os.path.exists(log_path) else []
    save_log = lambda: json.dump(log, open(log_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    entry = next((e for e in log if e["file"] == rel and e.get("pending")), None)
    if entry:
        print(f"retomando la tarea pendiente {entry['ids']}", flush=True)
    else:
        if len(log) >= int(cfg.get("max_per_project") or 4):
            raise SystemExit(f"Límite de {cfg.get('max_per_project')} generaciones de música por proyecto (ajustes -> Música)")
        model = a.model or cfg.get("model") or DEFAULT_MODEL
        body = {"action": "custom" if (lyrics or a.title) and not a.instrumental else "auto", "mv": model, "style": a.style,
                "instrumental": 1 if a.instrumental else 0}
        if body["action"] == "custom": body.update(lyrics=lyrics or None, title=a.title[:80])
        if a.gender: body["gender"] = a.gender
        rec = Call(proj, "musicful", {"method": "POST", "url": API + "/v1/music/generate", "body": body})
        entry = {"file": rel, "provider": "musicful", "model": model, "style": a.style, "title": a.title,
                 "instrumental": bool(body["instrumental"]), "ids": task_ids(call("POST", "/v1/music/generate", key, body, rec=rec)),
                 "pending": True, "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
        log.append(entry); save_log()
        print(f"tarea {entry['ids']} ({model}, {body['action']})", flush=True)
    t0 = time.time()
    rec = Call(proj, "musicful", {"method": "GET", "url": f"{API}/v1/music/tasks?ids={','.join(entry['ids'])}", "for": rel})
    songs = poll(key, entry["ids"], a.timeout, rec)
    files = []
    for i, song in enumerate(songs):
        dest = variant(out, i)
        save_audio(song["audio_url"], dest, rec)
        files.append({"file": os.path.relpath(dest, proj), "seconds": song.get("duration"), "song_id": song.get("song_id"),
                      "title": song.get("title"), "lyric": song.get("lyric")})
    entry.update(pending=False, songs=files); save_log()
    for f in files: print(f"{f['file']} ({f['seconds']} s)")
    print(f"listo en {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
