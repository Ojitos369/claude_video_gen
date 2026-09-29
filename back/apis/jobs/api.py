import os
import shutil
from core.bases.apis import AsyncApi, pln
from core.conf.settings import MYE, PROJECTS_DIR
from core.jobs.runner import Job, runner


def get_job(job_id):
    job = Job(os.path.basename(job_id))
    if not job.exists():
        raise MYE("El trabajo no existe")
    return job


class ListJobs(AsyncApi):
    async def main(self):
        jobs = []
        if os.path.isdir(PROJECTS_DIR):
            for name in os.listdir(PROJECTS_DIR):
                job = Job(name)
                if not job.exists() and os.path.isdir(job.dir):
                    job.adopt()      # project made outside the app (terminal): list it as finished
                if job.exists():
                    jobs.append(job.summary())
        jobs.sort(key=lambda j: j.get("created") or "", reverse=True)
        self.response = {"jobs": jobs}


class CreateJob(AsyncApi):
    async def get_post_data(self):
        pass   # multipart form, handled in main

    async def main(self):
        form = await self.request.form()
        prompt = (form.get("prompt") or "").strip()
        if not prompt:
            raise MYE("Escribe qué video quieres hacer")
        uploads = [(f.filename, f.read) for f in form.getlist("files") if getattr(f, "filename", None)]
        job = await runner.create((form.get("name") or "").strip(), prompt, uploads, form.get("model"), form.get("aspect"), form.get("aspect_text") or "", form.get("tools"), form.get("effort"))
        self.response = {"job": job.summary()}


class JobDetail(AsyncApi):
    async def main(self):
        self.response = {"job": get_job(self.data["job_id"]).detail()}


class JobEvents(AsyncApi):
    async def main(self):
        self.response = {"events": get_job(self.data["job_id"]).events(int(self.data.get("since", 0) or 0))}


class JobMessage(AsyncApi):
    async def main(self):
        job = get_job(self.data["job_id"])
        text = (self.data.get("text") or "").strip()
        if not text:
            raise MYE("Mensaje vacío")
        if job.meta().get("status") in ("running", "queued"):
            raise MYE("El trabajo sigue en proceso; espera a que termine o cancélalo")
        await runner.follow_up(job, text, self.data.get("model"), self.data.get("effort"))
        self.response = {"job": job.summary()}


class RenameJob(AsyncApi):
    """Changes the display name only: projects/<id>/ keeps its folder (Claude's session refers to that path)."""
    async def main(self):
        job = get_job(self.data["job_id"])
        name = (self.data.get("name") or "").strip()
        if not name:
            raise MYE("El nombre no puede estar vacío")
        await runner.rename(job, name)
        self.response = {"job": job.summary()}


class CancelJob(AsyncApi):
    async def main(self):
        job = get_job(self.data["job_id"])
        await runner.cancel(job)
        self.response = {"job": job.summary()}


class DeleteJob(AsyncApi):
    async def main(self):
        job = get_job(self.data["job_id"])
        if job.meta().get("status") in ("running", "queued"):
            raise MYE("Cancela el trabajo antes de borrarlo")
        shutil.rmtree(job.dir)
        self.response = {"deleted": job.id}
