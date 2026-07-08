"""FastAPI application entry point containing all core endpoints with multi-user SQLite support."""

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, BackgroundTasks, Query, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.config import settings, save_config_file, save_api_keys_to_config, load_config_file, get_api_keys_from_config
from app.schemas import (
    HealthResponse,
    StatusResponse,
    LLMConfigRequest,
    LLMConfigResponse,
    FeatureConfigRequest,
    FeatureConfigResponse,
    LanguageConfigRequest,
    LanguageConfigResponse,
    ApiKeyStatusResponse,
    ApiKeyProviderStatus,
    ApiKeysUpdateRequest,
    ApiKeysUpdateResponse,
    ResumeUploadResponse,
    ResumeListResponse,
    ResumeSummary,
    ResumeFetchResponse,
    ResumeFetchData,
    RawResume,
    ResumeData,
    normalize_resume_data,
    JobUploadRequest,
    JobUploadResponse,
    ImproveResumeRequest,
    ImproveResumeResponse,
    ImproveResumeData,
    ImproveResumeConfirmRequest,
    UpdateCoverLetterRequest,
    UpdateOutreachMessageRequest,
    UpdateTitleRequest,
    ResetDatabaseRequest,
    ScrapeJobRequest,
    ScrapeJobResponse,
)
from app.core import (
    db,
    check_llm_health,
    get_llm_config,
    parse_resume_to_json,
    extract_job_keywords,
    generate_job_title,
    improve_resume,
    calculate_resume_diff,
    parse_document,
    scrape_linkedin_job,
)

logger = logging.getLogger("app")

# Fix for Windows
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    yield
    try:
        db.close()
    except Exception as e:
        logger.error(f"Error closing database: {e}")

app = FastAPI(
    title="Resume Matcher API",
    description="Lean & Local AI-powered resume tailoring for job descriptions",
    version=__version__,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Helpers
async def run_resume_processing(resume_id: str, content: str, username: str = "default") -> None:
    try:
        db.update_resume(resume_id, {"processing_status": "processing"}, username=username)
        parsed = await parse_resume_to_json(content)
        db.update_resume(resume_id, {
            "processed_data": parsed,
            "processing_status": "ready"
        }, username=username)
    except Exception as e:
        logger.error(f"Failed to process resume {resume_id} for user {username}: {e}")
        db.update_resume(resume_id, {"processing_status": "failed"}, username=username)

# ------------------------------------------
# HEALTH / SYSTEM ENDPOINTS
# ------------------------------------------

@app.get("/")
async def root():
    return {
        "name": "Resume Matcher API",
        "version": __version__,
        "docs": "/docs",
    }

@app.get("/api/v1/health", response_model=HealthResponse)
async def health():
    cfg = get_llm_config()
    health_check = await check_llm_health(cfg)
    return HealthResponse(
        status="healthy",
        llm={
            "provider": cfg.provider,
            "model": cfg.model,
            "healthy": health_check.get("healthy", False),
            "error_code": health_check.get("error_code")
        }
    )

@app.get("/api/v1/status", response_model=StatusResponse)
async def status(username: str = "default"):
    cfg = get_llm_config()
    health_check = await check_llm_health(cfg)
    master = db.get_master_resume(username=username)
    return StatusResponse(
        status="healthy",
        llm_configured=bool(cfg.api_key or cfg.provider == "ollama"),
        llm_healthy=health_check.get("healthy", False),
        has_master_resume=master is not None,
        database_stats=db.get_stats(username=username)
    )

# ------------------------------------------
# CONFIGURATION ENDPOINTS
# ------------------------------------------

@app.get("/api/v1/config/llm-api-key", response_model=LLMConfigResponse)
async def get_config_llm():
    cfg = get_llm_config()
    masked = f"...{cfg.api_key[-4:]}" if len(cfg.api_key) > 4 else ""
    return LLMConfigResponse(
        provider=cfg.provider,
        model=cfg.model,
        api_key=masked,
        api_base=cfg.api_base
    )

@app.put("/api/v1/config/llm-api-key", response_model=LLMConfigResponse)
async def put_config_llm(req: LLMConfigRequest):
    stored = load_config_file()
    if req.provider is not None:
        stored["provider"] = req.provider
    if req.model is not None:
        stored["model"] = req.model
    if req.api_key is not None:
        stored["api_key"] = req.api_key
        # Sync with api_keys nested map
        api_keys = stored.get("api_keys", {})
        prov_map = {
            "openai": "openai",
            "anthropic": "anthropic",
            "gemini": "google",
            "openrouter": "openrouter",
            "deepseek": "deepseek",
            "ollama": "ollama",
        }
        prov = req.provider or stored.get("provider", "openai")
        mapped_prov = prov_map.get(prov, prov)
        api_keys[mapped_prov] = req.api_key
        stored["api_keys"] = api_keys
    if req.api_base is not None:
        stored["api_base"] = req.api_base
    save_config_file(stored)
    cfg = get_llm_config()
    masked = f"...{cfg.api_key[-4:]}" if len(cfg.api_key) > 4 else ""
    return LLMConfigResponse(
        provider=cfg.provider,
        model=cfg.model,
        api_key=masked,
        api_base=cfg.api_base
    )

@app.post("/api/v1/config/llm-test")
async def test_llm(req: LLMConfigRequest):
    cfg = get_llm_config()
    test_config = get_llm_config()
    if req.provider:
        test_config.provider = req.provider
    if req.model:
        test_config.model = req.model
    if req.api_key:
        test_config.api_key = req.api_key
    if req.api_base:
        test_config.api_base = req.api_base
    res = await check_llm_health(test_config, include_details=True)
    return res

@app.get("/api/v1/config/features", response_model=FeatureConfigResponse)
async def get_config_features():
    stored = load_config_file()
    return FeatureConfigResponse(
        enable_cover_letter=stored.get("enable_cover_letter", False),
        enable_outreach_message=stored.get("enable_outreach_message", False)
    )

@app.put("/api/v1/config/features", response_model=FeatureConfigResponse)
async def put_config_features(req: FeatureConfigRequest):
    stored = load_config_file()
    if req.enable_cover_letter is not None:
        stored["enable_cover_letter"] = req.enable_cover_letter
    if req.enable_outreach_message is not None:
        stored["enable_outreach_message"] = req.enable_outreach_message
    save_config_file(stored)
    return FeatureConfigResponse(
        enable_cover_letter=stored.get("enable_cover_letter"),
        enable_outreach_message=stored.get("enable_outreach_message")
    )

@app.get("/api/v1/config/language", response_model=LanguageConfigResponse)
async def get_config_language():
    stored = load_config_file()
    return LanguageConfigResponse(
        ui_language=stored.get("ui_language", "en"),
        content_language=stored.get("content_language", "en")
    )

@app.put("/api/v1/config/language", response_model=LanguageConfigResponse)
async def put_config_language(req: LanguageConfigRequest):
    stored = load_config_file()
    if req.ui_language is not None:
        stored["ui_language"] = req.ui_language
    if req.content_language is not None:
        stored["content_language"] = req.content_language
    save_config_file(stored)
    return LanguageConfigResponse(
        ui_language=stored.get("ui_language"),
        content_language=stored.get("content_language")
    )

@app.get("/api/v1/config/api-keys", response_model=ApiKeyStatusResponse)
async def get_config_api_keys():
    keys = get_api_keys_from_config()
    providers = ["openai", "anthropic", "google", "openrouter", "deepseek"]
    statuses = []
    for p in providers:
        key = keys.get(p)
        statuses.append(ApiKeyProviderStatus(
            provider=p,
            configured=bool(key),
            masked_key=f"...{key[-4:]}" if key and len(key) > 4 else None
        ))
    return ApiKeyStatusResponse(providers=statuses)

@app.post("/api/v1/config/api-keys", response_model=ApiKeysUpdateResponse)
async def post_config_api_keys(req: ApiKeysUpdateRequest):
    keys = get_api_keys_from_config()
    updated = []
    if req.openai is not None:
        keys["openai"] = req.openai
        updated.append("openai")
    if req.anthropic is not None:
        keys["anthropic"] = req.anthropic
        updated.append("anthropic")
    if req.google is not None:
        keys["google"] = req.google
        updated.append("google")
    if req.openrouter is not None:
        keys["openrouter"] = req.openrouter
        updated.append("openrouter")
    if req.deepseek is not None:
        keys["deepseek"] = req.deepseek
        updated.append("deepseek")
    save_api_keys_to_config(keys)
    return ApiKeysUpdateResponse(message="API keys updated", updated_providers=updated)

@app.post("/api/v1/config/reset")
async def post_config_reset(req: ResetDatabaseRequest, username: str = "default"):
    if not req.confirm or req.confirm.lower() != "confirm":
        raise HTTPException(status_code=400, detail="Must provide confirmation")
    db.reset_database(username=username)
    return {"message": f"Database and config reset complete for user {username}"}

# ------------------------------------------
# RESUMES ENDPOINTS
# ------------------------------------------

@app.post("/api/v1/resumes/upload", response_model=ResumeUploadResponse)
async def upload_resume(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    username: str = "default",
):
    try:
        content_bytes = await file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read file: {e}")
        
    if not content_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    try:
        markdown_content = await parse_document(content_bytes, file.filename or "resume.pdf")
    except Exception as e:
        logger.error(f"Failed to parse document: {e}")
        raise HTTPException(status_code=422, detail="Failed to parse document. Please upload a valid PDF or DOCX.")

    resume_doc = await db.create_resume_atomic_master(
        content=markdown_content,
        filename=file.filename or "resume.md",
        processing_status="pending",
        username=username
    )
    background_tasks.add_task(run_resume_processing, resume_doc["resume_id"], markdown_content, username)
    return ResumeUploadResponse(
        message="Resume upload received and processing started",
        request_id=str(uuid4()),
        resume_id=resume_doc["resume_id"],
        processing_status="pending",
        is_master=resume_doc["is_master"]
    )

@app.get("/api/v1/resumes/list", response_model=ResumeListResponse)
async def list_resumes(username: str = "default"):
    resumes = db.list_resumes(username=username)
    summaries = []
    for r in resumes:
        summaries.append(ResumeSummary(
            resume_id=r["resume_id"],
            filename=r.get("filename"),
            is_master=r.get("is_master", False),
            parent_id=r.get("parent_id"),
            processing_status=r.get("processing_status", "pending"),
            created_at=r["created_at"],
            updated_at=r["updated_at"],
            title=r.get("title")
        ))
    return ResumeListResponse(request_id=str(uuid4()), data=summaries)

@app.get("/api/v1/resumes", response_model=ResumeFetchResponse)
async def get_resume_by_query(resume_id: str | None = None, username: str = "default"):
    if not resume_id:
        raise HTTPException(status_code=400, detail="Missing resume_id query parameter")
    r = db.get_resume(resume_id, username=username)
    if not r:
        raise HTTPException(status_code=404, detail="Resume not found")
    processed = None
    if r.get("processed_data"):
        # lazy metadata migration if needed
        migrated = normalize_resume_data(r["processed_data"])
        processed = ResumeData.model_validate(migrated)

    return ResumeFetchResponse(
        request_id=str(uuid4()),
        data=ResumeFetchData(
            resume_id=r["resume_id"],
            raw_resume=RawResume(
                id=None,
                content=r["content"],
                content_type=r.get("content_type", "md"),
                created_at=r["created_at"],
                processing_status=r.get("processing_status", "ready")
            ),
            processed_resume=processed,
            cover_letter=r.get("cover_letter"),
            outreach_message=r.get("outreach_message"),
            parent_id=r.get("parent_id"),
            title=r.get("title")
        )
    )

@app.get("/api/v1/resumes/{resume_id}", response_model=ResumeFetchResponse)
async def get_resume(resume_id: str, username: str = "default"):
    return await get_resume_by_query(resume_id=resume_id, username=username)

@app.patch("/api/v1/resumes/{resume_id}", response_model=ResumeFetchResponse)
async def patch_resume(resume_id: str, updates: dict[str, Any], username: str = "default"):
    r = db.get_resume(resume_id, username=username)
    if not r:
        raise HTTPException(status_code=404, detail="Resume not found")
    
    # Extract only the processed_resume payload if provided nested under processed_resume or processed_data
    payload = updates
    if "processed_resume" in updates:
        payload = updates["processed_resume"]
    elif "processed_data" in updates:
        payload = updates["processed_data"]

    # Validate schema
    try:
        validated = ResumeData.model_validate(payload)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid resume format: {e}")

    # Save to database
    db.update_resume(resume_id, {"processed_data": validated.model_dump()}, username=username)
    return await get_resume(resume_id, username=username)

@app.delete("/api/v1/resumes/{resume_id}")
async def delete_resume(resume_id: str, username: str = "default"):
    success = db.delete_resume(resume_id, username=username)
    if not success:
        raise HTTPException(status_code=404, detail="Resume not found")
    return {"message": f"Resume {resume_id} deleted successfully"}

@app.post("/api/v1/resumes/improve/preview", response_model=ImproveResumeResponse)
@app.post("/api/v1/resumes/improve", response_model=ImproveResumeResponse)
async def improve_resume_endpoint(req: ImproveResumeRequest, username: str = "default"):
    res = db.get_resume(req.resume_id, username=username)
    if not res:
        raise HTTPException(status_code=404, detail="Resume not found")
    job = db.get_job(req.job_id, username=username)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    orig_data = res.get("processed_data") or {}
    orig_text = res.get("content") or ""

    try:
        keywords = await extract_job_keywords(job["content"])
        improved_dict = await improve_resume(orig_text, job["content"], keywords)
        title = await generate_job_title(job["content"])
        
        # Calculate diffs
        diff_summary, detailed_changes = calculate_resume_diff(orig_data, improved_dict)

        # Build response payload
        preview_data = ImproveResumeData(
            request_id=str(uuid4()),
            resume_id=None, # Null in preview until confirmed & saved
            job_id=req.job_id,
            resume_preview=ResumeData.model_validate(improved_dict),
            improvements=[ImprovementSuggestion(suggestion=f"Aligned with {title}", lineNumber=0)],
            diff_summary=diff_summary,
            detailed_changes=detailed_changes,
            refinement_successful=True
        )
        return ImproveResumeResponse(request_id=preview_data.request_id, data=preview_data)
    except Exception as e:
        logger.error(f"Tailoring failed: {e}")
        raise HTTPException(status_code=500, detail="Tailoring failed. Please check LLM keys and try again.")

@app.post("/api/v1/resumes/improve/confirm", response_model=ImproveResumeResponse)
async def confirm_improve(req: ImproveResumeConfirmRequest, username: str = "default"):
    orig = db.get_resume(req.resume_id, username=username)
    if not orig:
        raise HTTPException(status_code=404, detail="Original resume not found")
    job = db.get_job(req.job_id, username=username)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    title = await generate_job_title(job["content"])

    # Create tailored resume
    tailored = db.create_resume(
        content=orig["content"], # raw markdown
        filename=f"Tailored - {title}.md",
        parent_id=req.resume_id,
        processed_data=req.improved_data.model_dump(),
        processing_status="ready",
        title=title,
        username=username
    )

    # Save improvement record
    db.create_improvement(
        original_resume_id=req.resume_id,
        tailored_resume_id=tailored["resume_id"],
        job_id=req.job_id,
        improvements=[imp.model_dump() for idx, imp in enumerate(req.improvements)],
        username=username
    )

    preview_data = ImproveResumeData(
        request_id=str(uuid4()),
        resume_id=tailored["resume_id"],
        job_id=req.job_id,
        resume_preview=req.improved_data,
        improvements=req.improvements,
        refinement_successful=True
    )
    return ImproveResumeResponse(request_id=preview_data.request_id, data=preview_data)

@app.post("/api/v1/resumes/{resume_id}/retry-processing", response_model=ResumeUploadResponse)
async def retry_processing(resume_id: str, background_tasks: BackgroundTasks, username: str = "default"):
    rer = db.get_resume(resume_id, username=username)
    import pdb; pdb.set_trace()
    if not rer:
        raise HTTPException(status_code=404, detail="Resume not found")
    
    if rer.get("processing_status") not in ("failed", "processing", "pending", "ready"):
        raise HTTPException(
            status_code=400,
            detail="Only resumes with 'failed', 'pending', or 'processing' status can be retried."
        )
        
    markdown_content = rer.get("content", "")
    if not markdown_content:
        raise HTTPException(
            status_code=400,
            detail="Resume has no stored content to re-process."
        )
        
    # Update status to pending
    db.update_resume(resume_id, {"processing_status": "pending"}, username=username)
    
    background_tasks.add_task(run_resume_processing, resume_id, markdown_content, username)
    return ResumeUploadResponse(
        message="Retry processing started",
        request_id=str(uuid4()),
        resume_id=resume_id,
        processing_status="pending",
        is_master=rer.get("is_master", False)
    )

# Backward-compatibility stubs for UI operations
@app.patch("/api/v1/resumes/{resume_id}/cover-letter")
async def update_cover_letter(resume_id: str, req: UpdateCoverLetterRequest, username: str = "default"):
    db.update_resume(resume_id, {"cover_letter": req.content}, username=username)
    return {"message": "Cover letter updated successfully"}

@app.patch("/api/v1/resumes/{resume_id}/outreach-message")
async def update_outreach_message(resume_id: str, req: UpdateOutreachMessageRequest, username: str = "default"):
    db.update_resume(resume_id, {"outreach_message": req.content}, username=username)
    return {"message": "Outreach message updated successfully"}

@app.patch("/api/v1/resumes/{resume_id}/title")
async def update_title(resume_id: str, req: UpdateTitleRequest, username: str = "default"):
    db.update_resume(resume_id, {"title": req.title}, username=username)
    return {"message": "Title updated successfully"}

# ------------------------------------------
# JOBS ENDPOINTS
# ------------------------------------------

@app.post("/api/v1/jobs/scrape", response_model=ScrapeJobResponse)
async def scrape_job(req: ScrapeJobRequest):
    try:
        desc = await scrape_linkedin_job(req.url)
        return ScrapeJobResponse(description=desc)
    except Exception as e:
        logger.error(f"Scraping failed for URL {req.url}: {e}")
        raise HTTPException(status_code=422, detail=f"Failed to parse LinkedIn job URL: {e}")

@app.post("/api/v1/jobs/upload", response_model=JobUploadResponse)
async def upload_job(req: JobUploadRequest, username: str = "default"):
    if not req.job_descriptions:
        raise HTTPException(status_code=400, detail="No job descriptions provided")
    
    # Store first job description
    content = req.job_descriptions[0]
    job_doc = db.create_job(content=content, resume_id=req.resume_id, username=username)
    return JobUploadResponse(
        message="Job description uploaded successfully",
        job_id=[job_doc["job_id"]],
        request={"job_descriptions": req.job_descriptions, "resume_id": req.resume_id}
    )

@app.get("/api/v1/jobs/{job_id}")
async def get_job_endpoint(job_id: str, username: str = "default"):
    j = db.get_job(job_id, username=username)
    if not j:
        raise HTTPException(status_code=404, detail="Job not found")
    return j

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=True)
