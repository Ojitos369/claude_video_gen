from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import FileResponse
from .api import ListJobs, CreateJob, JobDetail, JobEvents, JobMessage, CancelJob, DeleteJob, RenameJob, get_job

router = APIRouter()

@router.get("/list")
async def list_jobs(request: Request):
    return await ListJobs(request=request).run()

@router.post("/create")
async def create_job(request: Request):
    return await CreateJob(request=request).run()

@router.get("/detail/{job_id}")
async def job_detail(request: Request, job_id: str):
    return await JobDetail(request=request, job_id=job_id).run()

@router.get("/events/{job_id}")
async def job_events(request: Request, job_id: str):
    return await JobEvents(request=request, job_id=job_id).run()

@router.post("/message/{job_id}")
async def job_message(request: Request, job_id: str):
    return await JobMessage(request=request, job_id=job_id).run()

@router.post("/rename/{job_id}")
async def rename_job(request: Request, job_id: str):
    return await RenameJob(request=request, job_id=job_id).run()

@router.post("/cancel/{job_id}")
async def cancel_job(request: Request, job_id: str):
    return await CancelJob(request=request, job_id=job_id).run()

@router.post("/delete/{job_id}")
async def delete_job(request: Request, job_id: str):
    return await DeleteJob(request=request, job_id=job_id).run()

@router.get("/file/{job_id}/{path:path}")
async def job_file(job_id: str, path: str):
    """Project files (videos with range requests, so the player can seek)."""
    try:
        p = get_job(job_id).safe_path(path)
    except Exception:
        p = None
    if not p:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    return FileResponse(p)
