# Claude Code hook (PostToolUse / Stop) for a running job: delivers the messages the user sent from the app while Claude works.
# The backend appends them to projects/<id>/.app/inbox.jsonl; this script takes the file (atomic rename), and hands the text to
# Claude: as additionalContext after a tool call, or blocking the stop so Claude keeps working with it. Stdlib only.
# Usage: python inbox_hook.py <inbox.jsonl> <PostToolUse|Stop>
import json
import os
import sys


def take(path):
    tmp = f"{path}.{os.getpid()}"
    try:
        os.replace(path, tmp)
    except OSError:
        return []
    with open(tmp, encoding="utf-8") as f:
        msgs = [json.loads(line) for line in f if line.strip()]
    with open(os.path.join(os.path.dirname(path), "inbox-entregados.jsonl"), "a", encoding="utf-8") as f:
        f.writelines(json.dumps(m, ensure_ascii=False) + "\n" for m in msgs)
    os.remove(tmp)
    return msgs


def main():
    path, event = sys.argv[1], sys.argv[2]
    try:
        sys.stdin.read()
    except Exception:
        pass
    msgs = take(path)
    if not msgs:
        return
    text = ("El usuario envió desde la app un mensaje mientras trabajabas. Complementa el pedido: tenlo en cuenta desde ahora "
            "(ajusta el plan y lo ya hecho si hace falta, sin rehacer lo que no cambia) y anótalo en PROGRESO.md.\n\n"
            + "\n\n".join(f"Mensaje: {m['text']}" + (f"\nArchivos nuevos en el proyecto: {', '.join(m['files'])}" if m.get("files") else "")
                          for m in msgs))
    if event == "Stop":
        out = {"decision": "block", "reason": text}
    else:
        out = {"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}
    sys.stdout.write(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
