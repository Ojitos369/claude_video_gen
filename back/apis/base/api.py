import os
import shutil
import subprocess
from core.bases.apis import BaseApi, pln, prod_mode, dev_mode
from core.conf.settings import CLAUDE_BIN, CLAUDE_MODEL, CLAUDE_MODELS, CLAUDE_EFFORT, CLAUDE_EFFORTS, WORKSPACE_DIR


class HelloWorld(BaseApi):
    def main(self):
        self.show_me()
        self.response = {"Hello": "World", "message": "Hello World"}

    def validate_session(self):
        pass


class GetModes(BaseApi):
    def main(self):
        self.response = {"prod_mode": prod_mode, "dev_mode": dev_mode}

    def validate_session(self):
        pass


class Status(BaseApi):
    """Environment check shown by the front: claude CLI, model, GPU, ffmpeg."""
    def main(self):
        claude = CLAUDE_BIN if os.path.isfile(CLAUDE_BIN) else shutil.which(CLAUDE_BIN)
        version = ""
        if claude:
            try:
                from core.conf.claude_bin import command
                version = subprocess.run(command(claude) + ["--version"], capture_output=True, text=True, timeout=20).stdout.strip()
            except Exception:
                version = "?"
        gpu = ""
        if shutil.which("nvidia-smi"):
            try:
                gpu = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"], capture_output=True, text=True, timeout=10).stdout.strip()
            except Exception:
                pass
        from core.jobs.runner import runner
        self.response = {"claude": bool(claude), "claude_bin": claude, "claude_version": version, "model": CLAUDE_MODEL, "models": CLAUDE_MODELS, "effort": CLAUDE_EFFORT, "efforts": CLAUDE_EFFORTS, "workspace": WORKSPACE_DIR,
                         "gpu": gpu, "ffmpeg": bool(shutil.which("ffmpeg")), "queue": runner.queue.qsize(),
                         "running": list(runner.procs.keys())}

    def validate_session(self):
        pass
