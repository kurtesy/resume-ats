"""Database wrapper, LiteLLM wrapper, and resume tailoring/improvement core logic."""

import asyncio
import json
import logging
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4
from difflib import SequenceMatcher
from dataclasses import dataclass

from markitdown import MarkItDown
from playwright.async_api import async_playwright

import litellm

from app.config import settings
from app.schemas import (
    ResumeData,
    ResumeFieldDiff,
    ResumeDiffSummary
)

logger = logging.getLogger(__name__)

from sqlalchemy import create_engine, Column, String, Boolean, JSON, Integer, Text, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker

# ==========================================
# 1. DATABASE LAYER (SQLALCHEMY POSTGRESQL / SQLITE)
# ==========================================

db_url = settings.get_database_url()
is_postgres = db_url.startswith("postgres")

if is_postgres:
    engine = create_engine(db_url, echo=False, pool_pre_ping=True, pool_recycle=3600)
else:
    engine = create_engine(db_url, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class ResumeModel(Base):
    __tablename__ = "resumes"
    
    resume_id = Column(String, primary_key=True, index=True)
    username = Column(String, default="default", index=True)
    content = Column(Text, nullable=False)
    content_type = Column(String, default="md")
    filename = Column(String, nullable=True)
    is_master = Column(Boolean, default=False)
    parent_id = Column(String, nullable=True)
    processed_data = Column(JSON, nullable=True)
    processing_status = Column(String, default="pending")
    cover_letter = Column(Text, nullable=True)
    outreach_message = Column(Text, nullable=True)
    title = Column(String, nullable=True)
    created_at = Column(String, nullable=False)
    updated_at = Column(String, nullable=False)

class JobModel(Base):
    __tablename__ = "jobs"
    
    job_id = Column(String, primary_key=True, index=True)
    username = Column(String, default="default", index=True)
    content = Column(Text, nullable=False)
    resume_id = Column(String, nullable=True)
    created_at = Column(String, nullable=False)

class ImprovementModel(Base):
    __tablename__ = "improvements"
    
    request_id = Column(String, primary_key=True, index=True)
    username = Column(String, default="default", index=True)
    original_resume_id = Column(String, nullable=False)
    tailored_resume_id = Column(String, nullable=False)
    job_id = Column(String, nullable=False)
    improvements = Column(JSON, nullable=False)
    created_at = Column(String, nullable=False)

def _model_to_dict(model_instance) -> dict[str, Any] | None:
    if not model_instance:
        return None
    d = {}
    for column in model_instance.__table__.columns:
        d[column.name] = getattr(model_instance, column.name)
    return d

class Database:
    """SQLAlchemy database wrapper (PostgreSQL or SQLite) for resume matcher data."""

    _master_resume_lock = asyncio.Lock()

    def __init__(self):
        if not is_postgres:
            settings.data_dir.mkdir(parents=True, exist_ok=True)
        Base.metadata.create_all(bind=engine)

    def close(self) -> None:
        pass

    def create_resume(
        self,
        content: str,
        content_type: str = "md",
        filename: str | None = None,
        is_master: bool = False,
        parent_id: str | None = None,
        processed_data: dict[str, Any] | None = None,
        processing_status: str = "pending",
        cover_letter: str | None = None,
        outreach_message: str | None = None,
        title: str | None = None,
        username: str = "default",
    ) -> dict[str, Any]:
        resume_id = str(uuid4())
        now = datetime.now(timezone.utc).isoformat()
        
        db_resume = ResumeModel(
            resume_id=resume_id,
            username=username,
            content=content,
            content_type=content_type,
            filename=filename,
            is_master=is_master,
            parent_id=parent_id,
            processed_data=processed_data,
            processing_status=processing_status,
            cover_letter=cover_letter,
            outreach_message=outreach_message,
            title=title,
            created_at=now,
            updated_at=now,
        )
        
        with SessionLocal() as session:
            session.add(db_resume)
            session.commit()
            return _model_to_dict(db_resume)

    async def create_resume_atomic_master(
        self,
        content: str,
        content_type: str = "md",
        filename: str | None = None,
        processed_data: dict[str, Any] | None = None,
        processing_status: str = "pending",
        cover_letter: str | None = None,
        outreach_message: str | None = None,
        username: str = "default",
    ) -> dict[str, Any]:
        async with self._master_resume_lock:
            current_master = self.get_master_resume(username=username)
            is_master = current_master is None

            if current_master and current_master.get("processing_status") in ("failed", "processing"):
                with SessionLocal() as session:
                    session.query(ResumeModel).filter(
                        ResumeModel.resume_id == current_master["resume_id"],
                        ResumeModel.username == username
                    ).update({"is_master": False})
                    session.commit()
                is_master = True

            return self.create_resume(
                content=content,
                content_type=content_type,
                filename=filename,
                is_master=is_master,
                processed_data=processed_data,
                processing_status=processing_status,
                cover_letter=cover_letter,
                outreach_message=outreach_message,
                username=username,
            )

    def get_resume(self, resume_id: str, username: str = "default") -> dict[str, Any] | None:
        with SessionLocal() as session:
            res = session.query(ResumeModel).filter(
                ResumeModel.resume_id == resume_id,
                ResumeModel.username == username
            ).first()
            return _model_to_dict(res)

    def get_master_resume(self, username: str = "default") -> dict[str, Any] | None:
        with SessionLocal() as session:
            res = session.query(ResumeModel).filter(
                ResumeModel.is_master == True,
                ResumeModel.username == username
            ).first()
            return _model_to_dict(res)

    def update_resume(self, resume_id: str, updates: dict[str, Any], username: str = "default") -> dict[str, Any]:
        with SessionLocal() as session:
            res = session.query(ResumeModel).filter(
                ResumeModel.resume_id == resume_id,
                ResumeModel.username == username
            ).first()
            if not res:
                raise ValueError(f"Resume not found: {resume_id}")
            
            updates["updated_at"] = datetime.now(timezone.utc).isoformat()
            for k, v in updates.items():
                if hasattr(res, k):
                    setattr(res, k, v)
            
            session.commit()
            return _model_to_dict(res)

    def delete_resume(self, resume_id: str, username: str = "default") -> bool:
        with SessionLocal() as session:
            res = session.query(ResumeModel).filter(
                ResumeModel.resume_id == resume_id,
                ResumeModel.username == username
            ).first()
            if res:
                session.delete(res)
                session.commit()
                return True
            return False

    def list_resumes(self, username: str = "default") -> list[dict[str, Any]]:
        with SessionLocal() as session:
            items = session.query(ResumeModel).filter(
                ResumeModel.username == username
            ).all()
            return [_model_to_dict(item) for item in items]

    def set_master_resume(self, resume_id: str, username: str = "default") -> bool:
        with SessionLocal() as session:
            target = session.query(ResumeModel).filter(
                ResumeModel.resume_id == resume_id,
                ResumeModel.username == username
            ).first()
            if not target:
                return False
            
            # Unset other masters for this username
            session.query(ResumeModel).filter(
                ResumeModel.username == username,
                ResumeModel.is_master == True
            ).update({"is_master": False})
            
            target.is_master = True
            session.commit()
            return True

    def create_job(self, content: str, resume_id: str | None = None, username: str = "default") -> dict[str, Any]:
        job_id = str(uuid4())
        now = datetime.now(timezone.utc).isoformat()
        
        db_job = JobModel(
            job_id=job_id,
            username=username,
            content=content,
            resume_id=resume_id,
            created_at=now,
        )
        with SessionLocal() as session:
            session.add(db_job)
            session.commit()
            return _model_to_dict(db_job)

    def get_job(self, job_id: str, username: str = "default") -> dict[str, Any] | None:
        with SessionLocal() as session:
            res = session.query(JobModel).filter(
                JobModel.job_id == job_id,
                JobModel.username == username
            ).first()
            return _model_to_dict(res)

    def update_job(self, job_id: str, updates: dict[str, Any], username: str = "default") -> dict[str, Any] | None:
        with SessionLocal() as session:
            res = session.query(JobModel).filter(
                JobModel.job_id == job_id,
                JobModel.username == username
            ).first()
            if not res:
                return None
            for k, v in updates.items():
                if hasattr(res, k):
                    setattr(res, k, v)
            session.commit()
            return _model_to_dict(res)

    def create_improvement(
        self,
        original_resume_id: str,
        tailored_resume_id: str,
        job_id: str,
        improvements: list[dict[str, Any]],
        username: str = "default",
    ) -> dict[str, Any]:
        request_id = str(uuid4())
        now = datetime.now(timezone.utc).isoformat()
        
        db_imp = ImprovementModel(
            request_id=request_id,
            username=username,
            original_resume_id=original_resume_id,
            tailored_resume_id=tailored_resume_id,
            job_id=job_id,
            improvements=improvements,
            created_at=now,
        )
        with SessionLocal() as session:
            session.add(db_imp)
            session.commit()
            return _model_to_dict(db_imp)

    def get_improvement_by_tailored_resume(
        self, tailored_resume_id: str, username: str = "default"
    ) -> dict[str, Any] | None:
        with SessionLocal() as session:
            res = session.query(ImprovementModel).filter(
                ImprovementModel.tailored_resume_id == tailored_resume_id,
                ImprovementModel.username == username
            ).first()
            return _model_to_dict(res)

    def get_stats(self, username: str = "default") -> dict[str, Any]:
        with SessionLocal() as session:
            total_resumes = session.query(ResumeModel).filter(ResumeModel.username == username).count()
            total_jobs = session.query(JobModel).filter(JobModel.username == username).count()
            total_improvements = session.query(ImprovementModel).filter(ImprovementModel.username == username).count()
            has_master = session.query(ResumeModel).filter(
                ResumeModel.username == username,
                ResumeModel.is_master == True
            ).first() is not None
            
            return {
                "total_resumes": total_resumes,
                "total_jobs": total_jobs,
                "total_improvements": total_improvements,
                "has_master_resume": has_master,
            }

    def reset_database(self, username: str = "default") -> None:
        with SessionLocal() as session:
            session.query(ResumeModel).filter(ResumeModel.username == username).delete()
            session.query(JobModel).filter(JobModel.username == username).delete()
            session.query(ImprovementModel).filter(ImprovementModel.username == username).delete()
            session.commit()


db = Database()

# ==========================================
# 2. LITELLM / LLM WRAPPER LAYER
# ==========================================

LITELLM_LOGGER_NAMES = ("LiteLLM", "LiteLLM Router", "LiteLLM Proxy")

def _configure_litellm_logging() -> None:
    numeric_level = getattr(logging, settings.log_llm, logging.WARNING)
    for logger_name in LITELLM_LOGGER_NAMES:
        logging.getLogger(logger_name).setLevel(numeric_level)

_configure_litellm_logging()

LLM_TIMEOUT_HEALTH_CHECK = 30
LLM_TIMEOUT_COMPLETION = 120
LLM_TIMEOUT_JSON = 180

OPENROUTER_JSON_CAPABLE_MODELS = {
    "anthropic/claude-3-opus", "anthropic/claude-3-sonnet", "anthropic/claude-3-haiku",
    "anthropic/claude-3.5-sonnet", "anthropic/claude-3.5-haiku", "anthropic/claude-haiku-4-5-20251001",
    "anthropic/claude-sonnet-4-20250514", "anthropic/claude-opus-4-20250514",
    "openai/gpt-4-turbo", "openai/gpt-4", "openai/gpt-4o", "openai/gpt-4o-mini",
    "openai/gpt-3.5-turbo", "openai/gpt-5-nano-2025-08-07",
    "google/gemini-pro", "google/gemini-1.5-pro", "google/gemini-1.5-flash",
    "google/gemini-2.0-flash", "google/gemini-3-flash-preview",
    "deepseek/deepseek-chat", "deepseek/deepseek-reasoner",
    "mistralai/mistral-large", "mistralai/mistral-medium",
}

MAX_JSON_EXTRACTION_RECURSION = 10
MAX_JSON_CONTENT_SIZE = 1024 * 1024

class LLMConfig(BaseModel_from_schemas := Any): # placeholder to avoid pydantic circular import if any
    pass

@dataclass
class LocalLLMConfig:
    provider: str
    model: str
    api_key: str
    api_base: str | None = None

def _normalize_api_base(provider: str, api_base: str | None) -> str | None:
    if not api_base:
        return None
    base = api_base.strip()
    if not base:
        return None
    base = base.rstrip("/")
    if provider == "anthropic" and base.endswith("/v1"):
        base = base[: -len("/v1")].rstrip("/")
    if provider == "gemini" and base.endswith("/v1"):
        base = base[: -len("/v1")].rstrip("/")
    return base or None

def _extract_text_parts(value: Any, depth: int = 0, max_depth: int = 10) -> list[str]:
    if depth >= max_depth or value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        parts = []
        for item in value:
            parts.extend(_extract_text_parts(item, depth + 1, max_depth))
        return parts
    if isinstance(value, dict):
        if "text" in value:
            return _extract_text_parts(value.get("text"), depth + 1, max_depth)
        if "content" in value:
            return _extract_text_parts(value.get("content"), depth + 1, max_depth)
        if "value" in value:
            return _extract_text_parts(value.get("value"), depth + 1, max_depth)
        return []
    if hasattr(value, "text"):
        return _extract_text_parts(getattr(value, "text"), depth + 1, max_depth)
    if hasattr(value, "content"):
        return _extract_text_parts(getattr(value, "content"), depth + 1, max_depth)
    return []

def _join_text_parts(parts: list[str]) -> str | None:
    joined = "\n".join(part for part in parts if part).strip()
    return joined or None

def _extract_message_text(message: Any) -> str | None:
    content = getattr(message, "content", None) or (message.get("content") if isinstance(message, dict) else None)
    return _join_text_parts(_extract_text_parts(content))

def _extract_choice_text(choice: Any) -> str | None:
    message = getattr(choice, "message", None) or (choice.get("message") if isinstance(choice, dict) else None)
    content = _extract_message_text(message)
    if content:
        return content
    if hasattr(choice, "text"):
        content = _join_text_parts(_extract_text_parts(getattr(choice, "text")))
        if content:
            return content
    if isinstance(choice, dict) and "text" in choice:
        content = _join_text_parts(_extract_text_parts(choice.get("text")))
        if content:
            return content
    if hasattr(choice, "delta"):
        content = _join_text_parts(_extract_text_parts(getattr(choice, "delta")))
        if content:
            return content
    if isinstance(choice, dict) and "delta" in choice:
        content = _join_text_parts(_extract_text_parts(choice.get("delta")))
        if content:
            return content
    return None

def get_llm_config() -> LocalLLMConfig:
    stored = {}
    config_path = settings.config_path
    if config_path.exists():
        try:
            stored = json.loads(config_path.read_text())
        except Exception:
            pass
    return LocalLLMConfig(
        provider=stored.get("provider", settings.llm_provider),
        model=stored.get("model", settings.llm_model),
        api_key=stored.get("api_key", settings.get_effective_api_key()),
        api_base=stored.get("api_base", settings.llm_api_base),
    )

def get_model_name(config: LocalLLMConfig) -> str:
    provider_prefixes = {
        "openai": "",
        "anthropic": "anthropic/",
        "openrouter": "openrouter/",
        "gemini": "gemini/",
        "deepseek": "deepseek/",
        "ollama": "ollama/",
    }
    prefix = provider_prefixes.get(config.provider, "")
    if config.provider == "openrouter":
        if config.model.startswith("openrouter/"):
            return config.model
        return f"openrouter/{config.model}"
    known_prefixes = ["openrouter/", "anthropic/", "gemini/", "deepseek/", "ollama/"]
    if any(config.model.startswith(p) for p in known_prefixes):
        return config.model
    return f"{prefix}{config.model}" if prefix else config.model

def _supports_temperature(provider: str, model: str) -> bool:
    if "gpt-5" in model.lower():
        return False
    return True

def _get_reasoning_effort(provider: str, model: str) -> str | None:
    if "gpt-5" in model.lower():
        return "minimal"
    return None

async def check_llm_health(
    config: LocalLLMConfig | None = None,
    *,
    include_details: bool = False,
    test_prompt: str | None = None,
) -> dict[str, Any]:
    if config is None:
        config = get_llm_config()
    if config.provider != "ollama" and not config.api_key:
        return {
            "healthy": False,
            "provider": config.provider,
            "model": config.model,
            "error_code": "api_key_missing",
        }
    model_name = get_model_name(config)
    prompt = test_prompt or "Hi"
    try:
        kwargs: dict[str, Any] = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 16,
            "api_key": config.api_key,
            "api_base": _normalize_api_base(config.provider, config.api_base),
            "timeout": LLM_TIMEOUT_HEALTH_CHECK,
        }
        reasoning_effort = _get_reasoning_effort(config.provider, model_name)
        if reasoning_effort:
            kwargs["reasoning_effort"] = reasoning_effort

        response = await litellm.acompletion(**kwargs)
        content = _extract_choice_text(response.choices[0])
        if not content:
            return {
                "healthy": False,
                "provider": config.provider,
                "model": config.model,
                "response_model": getattr(response, "model", None) if response else None,
                "error_code": "empty_content",
                "message": "LLM returned empty response",
            }
        return {
            "healthy": True,
            "provider": config.provider,
            "model": config.model,
            "response_model": getattr(response, "model", None) if response else None,
        }
    except Exception as e:
        logger.exception("LLM health check failed")
        return {
            "healthy": False,
            "provider": config.provider,
            "model": config.model,
            "error_code": "health_check_failed",
            "message": str(e),
        }

async def complete(
    prompt: str,
    system_prompt: str | None = None,
    config: LocalLLMConfig | None = None,
    max_tokens: int = 4096,
    temperature: float = 0.7,
) -> str:
    if config is None:
        config = get_llm_config()
    model_name = get_model_name(config)
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    try:
        kwargs: dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "max_tokens": max_tokens,
            "api_key": config.api_key,
            "api_base": _normalize_api_base(config.provider, config.api_base),
            "timeout": LLM_TIMEOUT_COMPLETION,
        }
        if _supports_temperature(config.provider, model_name):
            kwargs["temperature"] = temperature
        reasoning_effort = _get_reasoning_effort(config.provider, model_name)
        if reasoning_effort:
            kwargs["reasoning_effort"] = reasoning_effort

        response = await litellm.acompletion(**kwargs)
        content = _extract_choice_text(response.choices[0])
        if not content:
            raise ValueError("Empty response from LLM")
        return content
    except Exception as e:
        logger.error(f"LLM completion failed: {e}")
        raise ValueError("LLM completion failed. Check configuration.") from e

def _supports_json_mode(provider: str, model: str) -> bool:
    if provider in ["openai", "anthropic", "gemini", "deepseek"]:
        return True
    if provider == "openrouter":
        return model in OPENROUTER_JSON_CAPABLE_MODELS
    return False

def _appears_truncated(data: dict) -> bool:
    if not isinstance(data, dict):
        return False
    for key in ["workExperience", "education", "skills"]:
        if key in data and data[key] == []:
            return True
    if "personalInfo" not in data:
        return True
    return False

def _get_retry_temperature(attempt: int) -> float:
    return [0.1, 0.3, 0.5, 0.7][min(attempt, 3)]

def _calculate_timeout(operation: str, max_tokens: int, provider: str) -> int:
    base = {"health_check": 30, "completion": 120, "json": 180}.get(operation, 120)
    token_factor = max(1.0, max_tokens / 4096)
    provider_factor = {"openai": 1.0, "anthropic": 1.2, "openrouter": 1.5, "ollama": 2.0}.get(provider, 1.0)
    return int(base * token_factor * provider_factor)

def _extract_json(content: str, _depth: int = 0) -> str:
    if _depth > MAX_JSON_EXTRACTION_RECURSION:
        raise ValueError("JSON extraction exceeded max recursion depth")
    if len(content) > MAX_JSON_CONTENT_SIZE:
        raise ValueError("Content too large for JSON extraction")

    original = content
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0]
    elif "```" in content:
        parts = content.split("```")
        if len(parts) >= 2:
            content = parts[1]
            if content.startswith(("json", "JSON")):
                content = content[4:]

    content = content.strip()
    if content.startswith("{"):
        depth = 0
        end_idx = -1
        in_string = False
        escape_next = False
        for i, char in enumerate(content):
            if escape_next:
                escape_next = False
                continue
            if char == "\\":
                escape_next = True
                continue
            if char == '"' and not escape_next:
                in_string = not in_string
                continue
            if in_string:
                continue
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    end_idx = i
                    break
        if end_idx != -1:
            return content[: end_idx + 1]

    start_idx = content.find("{")
    if start_idx > 0:
        return _extract_json(content[start_idx:], _depth + 1)
    raise ValueError(f"No JSON found in response preview: {original[:200]}")

async def complete_json(
    prompt: str,
    system_prompt: str | None = None,
    config: LocalLLMConfig | None = None,
    max_tokens: int = 4096,
    retries: int = 2,
) -> dict[str, Any]:
    if config is None:
        config = get_llm_config()
    model_name = get_model_name(config)
    json_system = (system_prompt or "") + "\n\nYou must respond with valid JSON only. No explanations, no markdown."
    messages = [
        {"role": "system", "content": json_system},
        {"role": "user", "content": prompt},
    ]
    use_json_mode = _supports_json_mode(config.provider, config.model)
    last_error = None
    for attempt in range(retries + 1):
        try:
            kwargs: dict[str, Any] = {
                "model": model_name,
                "messages": messages,
                "max_tokens": max_tokens,
                "api_key": config.api_key,
                "api_base": _normalize_api_base(config.provider, config.api_base),
                "timeout": _calculate_timeout("json", max_tokens, config.provider),
            }
            if _supports_temperature(config.provider, model_name):
                kwargs["temperature"] = _get_retry_temperature(attempt)
            reasoning_effort = _get_reasoning_effort(config.provider, model_name)
            if reasoning_effort:
                kwargs["reasoning_effort"] = reasoning_effort
            if use_json_mode:
                kwargs["response_format"] = {"type": "json_object"}

            response = await litellm.acompletion(**kwargs)
            content = _extract_choice_text(response.choices[0])
            if not content:
                raise ValueError("Empty response from LLM")

            json_str = _extract_json(content)
            result = json.loads(json_str)
            return result
        except Exception as e:
            last_error = e
            if attempt < retries:
                messages[-1]["content"] = prompt + "\n\nOutput ONLY a valid JSON object starting with { and ending with }."
                continue
            raise ValueError(f"Failed to parse JSON: {e}") from e
    raise ValueError(f"LLM json failed: {last_error}")

# ==========================================
# 3. PROMPT TEMPLATES & SCHEMAS
# ==========================================

RESUME_SCHEMA = """{ 
  "personalInfo": { 
    "name": "John Doe", 
    "title": "Software Engineer", 
    "email": "john@example.com", 
    "phone": "+1-555-0100", 
    "location": "San Francisco, CA", 
    "website": "https://johndoe.dev", 
    "linkedin": "linkedin.com/in/johndoe", 
    "github": "github.com/johndoe" 
  }, 
  "summary": "Experienced software engineer with 5+ years...", 
  "workExperience": [ 
    { 
      "id": 1, 
      "title": "Senior Software Engineer", 
      "company": "Tech Corp", 
      "location": "San Francisco, CA", 
      "years": "2020 - Present", 
      "description": [ 
        "Led development of microservices architecture", 
        "Improved system performance by 40%" 
      ] 
    } 
  ], 
  "education": [ 
    { 
      "id": 1, 
      "institution": "University of California", 
      "degree": "B.S. Computer Science", 
      "years": "2014 - 2018", 
      "description": "Graduated with honors" 
    } 
  ], 
  "personalProjects": [ 
    { 
      "id": 1, 
      "name": "Open Source Tool", 
      "role": "Creator & Maintainer", 
      "years": "2021 - Present", 
      "description": [ 
        "Built CLI tool with 1000+ GitHub stars" 
      ] 
    } 
  ], 
  "additional": { 
    "technicalSkills": ["Python", "JavaScript", "AWS", "Docker"], 
    "languages": ["English (Native)"], 
    "certificationsTraining": ["AWS Solutions Architect"], 
    "awards": ["Employee of the Year 2022"] 
  }, 
  "customSections": {} 
}"""

PARSE_RESUME_PROMPT = """You are parsing a resume into structured JSON. Output ONLY the JSON object, no other text, no markdown fences.

Extraction rules:
- Transcribe the candidate's real content faithfully. Copy names, titles, companies, dates, locations, and numbers EXACTLY as written. Do not paraphrase, summarize, correct, translate, or embellish.
- Never copy values from the format example below. It only shows the shape of the JSON; "John Doe", "Tech Corp", etc. are placeholders, not data.
- If a field is not present in the resume, use an empty string "" (or an empty array [] for list fields). Never invent, guess, or infer missing values.
- Split every experience/project bullet into a separate array item. Strip leading bullet characters ("-", "*", "•") and numbering.
- Preserve the original ordering of experiences, education, projects, and bullets.
- Map skills, languages, certifications, and awards into the correct `additional` sub-arrays. If a skill list is comma- or pipe-separated, split it into individual items.
- Keep the summary/objective text as written; do not rewrite it.

The JSON must match this exact structure (shape only, ignore the sample values):
{schema}

Resume to parse:
{resume_text}"""

EXTRACT_KEYWORDS_PROMPT = """You are an ATS (Applicant Tracking System) and technical recruiting analyst. Extract the job's requirements and its ATS-critical keywords as JSON. Output ONLY the JSON object, no other text, no markdown fences.

Extraction rules:
- Capture keywords using the EXACT surface form used in the job description (an ATS matches literal strings). If the JD writes "CI/CD", "K8s", or "React.js", keep it verbatim.
- When the JD gives both an acronym and its expansion (e.g. "Kubernetes (K8s)"), include BOTH forms as separate keywords so either can be matched.
- required_skills: hard skills, tools, languages, frameworks, and platforms the JD marks as required/must-have.
- preferred_skills: skills described as nice-to-have, preferred, bonus, or "a plus".
- keywords: additional ATS-relevant terms and phrases (methodologies, domains, certifications by name, notable soft skills). No duplicates of items already listed above.
- key_responsibilities: the core duties, phrased as short action statements.
- experience_years: the minimum total years of experience as an integer. Use 0 if unspecified.
- seniority_level: one of "intern", "junior", "mid", "senior", "lead", "principal", "manager", or "unspecified".
- Do not invent requirements that are not in the text. Deduplicate case-insensitively. Preserve the JD's original casing for each retained term.

Output in EXACTLY this JSON format:
{{
  "required_skills": ["Python", "AWS"],
  "preferred_skills": ["Kubernetes"],
  "experience_requirements": ["5+ years building distributed systems"],
  "education_requirements": ["Bachelor's in CS or equivalent"],
  "key_responsibilities": ["Lead a team of engineers"],
  "keywords": ["microservices", "CI/CD", "Agile"],
  "experience_years": 5,
  "seniority_level": "senior"
}}

Job description:
{job_description}"""

CRITICAL_TRUTHFULNESS_RULES = """CRITICAL TRUTHFULNESS RULES - NEVER VIOLATE. A false resume is worse than a weak one:
1. DO NOT add any skill, tool, technology, framework, language, or certification that is not explicitly present in the original resume, even if the job requires it.
2. DO NOT invent, add, or alter numeric achievements or metrics (percentages, dollar amounts, team sizes, user counts). Keep every number exactly as it appears in the original; if none exists, do not fabricate one.
3. DO NOT add or change company names, job titles, employment dates, degrees, or institutions.
4. DO NOT inflate seniority, scope, or ownership (e.g. changing "contributed to" into "led", or "assisted" into "owned") beyond what the original states.
5. DO NOT add responsibilities, projects, or accomplishments the candidate did not describe.
6. You MAY rephrase, reorder, and re-emphasize the candidate's real experience, and mirror the job's terminology ONLY for skills and work the candidate genuinely has. Reframing true content is allowed; inventing content is not.
7. When unsure whether something is supported by the original, leave it out.
"""

IMPROVE_RESUME_PROMPT_FULL = """You are an expert resume writer and ATS optimization specialist. Rewrite the candidate's resume so it targets the job below and passes automated ATS screening, while staying 100% truthful. Output ONLY the JSON object, no other text, no markdown fences.

{critical_truthfulness_rules}

ATS OPTIMIZATION:
- Mirror the job's exact terminology for skills and experience the candidate genuinely has. If the candidate knows "Kubernetes" and the JD says "K8s", use the JD's surface form. Matching literal strings is what an ATS scores.
- Weave the provided keywords into the summary, skills, and experience bullets NATURALLY. No keyword stuffing, no lists of disconnected terms, no repeating a keyword just to hit a count.
- Ensure required skills the candidate actually possesses appear in `additional.technicalSkills` using the JD's phrasing. Do not add skills the candidate lacks (see truthfulness rules).
- Keep standard, machine-readable section names; do not rename core sections.

SUMMARY (2-4 sentences):
- Open by positioning the candidate for THIS role, using the target job title/level where truthful.
- Front-load the most relevant real skills and the strongest quantified achievement that already exists in the resume.

EXPERIENCE BULLETS:
- Rewrite each bullet as: strong past-tense action verb + what was done + tool/skill + measurable impact (only if a metric already exists in the original).
- Lead with the accomplishments and technologies most relevant to the job; reorder bullets within a role to surface relevance.
- Vary action verbs; avoid weak openers ("Responsible for", "Worked on", "Helped with").
- Keep each bullet to one tight sentence.

PRIORITIZATION:
- Emphasize the experiences, projects, and skills most relevant to the job. Do not delete the candidate's real experience, but you may de-emphasize less relevant bullets by shortening them.

STYLE / ANTI-AI-DETECTION:
- Do NOT use the em dash ("—") anywhere. Use commas, periods, or parentheses.
- Avoid filler and AI-tell phrasing: "leveraged", "spearheaded", "dynamic", "results-driven", "passionate", "seamlessly", "cutting-edge", "in today's fast-paced world", "a proven track record".
- Write in a concise, professional, human voice. No first-person pronouns ("I", "my") in bullets.
- Preserve original date ranges exactly; do not modify years.

Job Description:
{job_description}

Keywords to emphasize (use the exact surface forms, only where truthful):
{job_keywords}

Original Resume:
{original_resume}

Output in this JSON format (shape only, do not copy the sample values):
{schema}"""

GENERATE_TITLE_PROMPT = """Extract the job title and hiring company from this job description.
Format the output as exactly "Role @ Company" (e.g., "Senior Frontend Engineer @ Stripe").
- Use the most specific role title stated in the posting.
- If the company name is not stated, output just the role with no "@".
- Do not add seniority, location, or any words that are not in the posting.
- Keep it under 60 characters.
Job Description:
{job_description}
Output the title line only, nothing else."""

# ==========================================
# 4. PARSING & IMPROVEMENT CORE LOGIC
# ==========================================

async def parse_document(content: bytes, filename: str) -> str:
    """Convert PDF/DOCX to Markdown using markitdown."""
    suffix = Path(filename).suffix.lower()
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    try:
        md = MarkItDown()
        result = md.convert(str(tmp_path))
        return result.text_content
    finally:
        tmp_path.unlink(missing_ok=True)

async def scrape_linkedin_job(url: str) -> str:
    """Scrapes job description from a LinkedIn job URL using HTTP client with a Playwright fallback."""
    import urllib.request
    from bs4 import BeautifulSoup
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    }
    
    try:
        req = urllib.request.Request(url, headers=headers)
        loop = asyncio.get_running_loop()
        def _fetch():
            with urllib.request.urlopen(req, timeout=12) as response:
                return response.read()
        
        html_bytes = await loop.run_in_executor(None, _fetch)
        html = html_bytes.decode('utf-8', errors='ignore')
        
        soup = BeautifulSoup(html, 'html.parser')
        desc_el = (
            soup.find(class_='show-more-less-html__markup') or 
            soup.find(class_='jobs-description__content') or 
            soup.find(class_='jobs-description-content__text') or
            soup.find(class_='description__text') or
            soup.find('main')
        )
        
        if desc_el:
            text = desc_el.get_text('\n').strip()
            if len(text) > 100:
                clean_text = re.sub(r'\n{3,}', '\n\n', text)
                return clean_text
    except Exception as fetch_err:
        logger.warning(f"Lightweight HTTP fetch failed: {fetch_err}. Falling back to Playwright...")

    # Fallback to Playwright if guest fetch was blocked or failed
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = await context.new_page()
        try:
            await page.goto(url, timeout=20000, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
            
            selectors = [
                ".show-more-less-html__markup",
                ".jobs-description__content",
                ".jobs-description-content__text",
                ".core-section-container__content",
                ".description__text",
                "main"
            ]
            
            text = ""
            for sel in selectors:
                locator = page.locator(sel)
                if await locator.count() > 0:
                    text = await locator.first.inner_text()
                    if text.strip() and len(text.strip()) > 100:
                        break
            
            if not text.strip():
                text = await page.inner_text("body")
                
            clean_text = text.strip()
            if not clean_text:
                raise ValueError("Could not extract any text content from the URL")
                
            clean_text = re.sub(r'\n{3,}', '\n\n', clean_text)
            return clean_text
        except Exception as e:
            logger.error(f"Playwright scraping failed: {e}")
            raise ValueError(f"Failed to scrape LinkedIn job: {e}")
        finally:
            await browser.close()

_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"disregard\s+(all\s+)?above",
    r"forget\s+(everything|all)",
    r"new\s+instructions?:",
    r"system\s*:",
]

def _sanitize_user_input(text: str) -> str:
    sanitized = text
    for pattern in _INJECTION_PATTERNS:
        sanitized = re.sub(pattern, "[REDACTED]", sanitized, flags=re.IGNORECASE)
    return sanitized

def _check_for_truncation(data: dict[str, Any]) -> None:
    if "personalInfo" not in data:
        raise ValueError("Missing required section: personalInfo")

async def parse_resume_to_json(resume_text: str) -> dict[str, Any]:
    sanitized = _sanitize_user_input(resume_text)
    prompt = PARSE_RESUME_PROMPT.format(schema=RESUME_SCHEMA, resume_text=sanitized)
    return await complete_json(
        prompt,
        "You are a precise resume parser. You transcribe the candidate's content faithfully into JSON and never invent, embellish, or omit information.",
    )

async def extract_job_keywords(job_description: str) -> dict[str, Any]:
    sanitized = _sanitize_user_input(job_description)
    prompt = EXTRACT_KEYWORDS_PROMPT.format(job_description=sanitized)
    return await complete_json(
        prompt,
        "You are an expert ATS and technical recruiting analyst. You extract requirements and ATS-critical keywords using the exact surface forms found in the job description.",
    )

async def generate_job_title(job_description: str) -> str:
    sanitized = _sanitize_user_input(job_description)
    prompt = GENERATE_TITLE_PROMPT.format(job_description=sanitized)
    title = await complete(prompt, "You are a precise title parser. You output only a single 'Role @ Company' line with no extra words.")
    return title.strip().strip('"').strip("'")

async def improve_resume(
    original_resume: str,
    job_description: str,
    job_keywords: dict[str, Any],
) -> dict[str, Any]:
    sanitized_jd = _sanitize_user_input(job_description)
    prompt = IMPROVE_RESUME_PROMPT_FULL.format(
        critical_truthfulness_rules=CRITICAL_TRUTHFULNESS_RULES,
        job_description=sanitized_jd,
        job_keywords=json.dumps(job_keywords, indent=2),
        original_resume=original_resume,
        schema=RESUME_SCHEMA,
    )
    result = await complete_json(
        prompt,
        "You are an expert resume writer and ATS optimization specialist. You tailor resumes to job descriptions truthfully, never fabricating skills or experience, and output valid JSON.",
        max_tokens=8192,
    )
    _check_for_truncation(result)
    validated = ResumeData.model_validate(result)
    return validated.model_dump()

# ==========================================
# 5. DIFF GENERATION LOGIC
# ==========================================

@dataclass(frozen=True)
class DiffConfidence:
    added: str
    removed: str
    modified: str

def _format_entry_label(parts: list[str], fallback: str) -> str:
    label = " | ".join([part for part in parts if part])
    return label if label else fallback

def _format_experience_entry(entry: dict[str, Any], index: int) -> str:
    return _format_entry_label([entry.get("title", ""), entry.get("company", ""), entry.get("years", "")], f"Work experience #{index + 1}")

def _format_education_entry(entry: dict[str, Any], index: int) -> str:
    return _format_entry_label([entry.get("degree", ""), entry.get("institution", ""), entry.get("years", "")], f"Education #{index + 1}")

def _format_project_entry(entry: dict[str, Any], index: int) -> str:
    return _format_entry_label([entry.get("name", ""), entry.get("role", ""), entry.get("years", "")], f"Project #{index + 1}")

def _normalize_string_list(value: Any, field_name: str) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized = []
    for item in value:
        if isinstance(item, str):
            stripped = item.strip()
            if stripped:
                normalized.append(stripped)
        elif isinstance(item, dict):
            candidate = item.get("name") or item.get("label") or item.get("value")
            if isinstance(candidate, str):
                stripped = candidate.strip()
                if stripped:
                    normalized.append(stripped)
    return normalized

def _build_string_index(value: Any, field_name: str) -> dict[str, str]:
    items = _normalize_string_list(value, field_name)
    index = {}
    for item in items:
        key = item.casefold()
        if key not in index:
            index[key] = item
    return index

def _extract_description_list(entry: Any) -> list[str]:
    if not isinstance(entry, dict):
        return []
    return _normalize_string_list(entry.get("description", []), "workExperience.description")

def _append_list_changes(
    changes: list[ResumeFieldDiff],
    field_path: str,
    field_type: str,
    original_items: list[str],
    improved_items: list[str],
    confidences: DiffConfidence,
) -> None:
    matcher = SequenceMatcher(a=original_items, b=improved_items, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if tag == "delete":
            for item in original_items[i1:i2]:
                changes.append(ResumeFieldDiff(field_path=field_path, field_type=field_type, change_type="removed", original_value=item, confidence=confidences.removed))
        elif tag == "insert":
            for item in improved_items[j1:j2]:
                changes.append(ResumeFieldDiff(field_path=field_path, field_type=field_type, change_type="added", new_value=item, confidence=confidences.added))
        elif tag == "replace":
            original_segment = original_items[i1:i2]
            improved_segment = improved_items[j1:j2]
            segment_len = max(len(original_segment), len(improved_segment))
            for offset in range(segment_len):
                original_value = original_segment[offset] if offset < len(original_segment) else None
                new_value = improved_segment[offset] if offset < len(improved_segment) else None
                if original_value is not None and new_value is not None:
                    changes.append(ResumeFieldDiff(field_path=field_path, field_type=field_type, change_type="modified", original_value=original_value, new_value=new_value, confidence=confidences.modified))
                elif new_value is not None:
                    changes.append(ResumeFieldDiff(field_path=field_path, field_type=field_type, change_type="added", new_value=new_value, confidence=confidences.added))
                elif original_value is not None:
                    changes.append(ResumeFieldDiff(field_path=field_path, field_type=field_type, change_type="removed", original_value=original_value, confidence=confidences.removed))

def calculate_resume_diff(original: dict[str, Any], improved: dict[str, Any]) -> tuple[ResumeDiffSummary, list[ResumeFieldDiff]]:
    changes = []
    original_summary = (original.get("summary") or "").strip()
    improved_summary = (improved.get("summary") or "").strip()
    if original_summary != improved_summary:
        changes.append(ResumeFieldDiff(
            field_path="summary",
            field_type="summary",
            change_type="modified" if original_summary and improved_summary else ("added" if improved_summary else "removed"),
            original_value=original_summary or None,
            new_value=improved_summary or None,
            confidence="medium"
        ))

    orig_skills = _build_string_index(original.get("additional", {}).get("technicalSkills", []), "additional.technicalSkills")
    new_skills = _build_string_index(improved.get("additional", {}).get("technicalSkills", []), "additional.technicalSkills")
    for s in set(new_skills) - set(orig_skills):
        changes.append(ResumeFieldDiff(field_path="additional.technicalSkills", field_type="skill", change_type="added", new_value=new_skills[s], confidence="high"))
    for s in set(orig_skills) - set(new_skills):
        changes.append(ResumeFieldDiff(field_path="additional.technicalSkills", field_type="skill", change_type="removed", original_value=orig_skills[s], confidence="medium"))

    original_experiences = original.get("workExperience", [])
    improved_experiences = improved.get("workExperience", [])
    max_experience_len = max(len(original_experiences), len(improved_experiences))
    confidences = DiffConfidence(added="medium", removed="low", modified="medium")
    for idx in range(max_experience_len):
        original_entry = original_experiences[idx] if idx < len(original_experiences) else None
        improved_entry = improved_experiences[idx] if idx < len(improved_experiences) else None
        _append_list_changes(
            changes,
            field_path=f"workExperience[{idx}].description",
            field_type="description",
            original_items=_extract_description_list(original_entry),
            improved_items=_extract_description_list(improved_entry),
            confidences=confidences,
        )

    orig_certs = _build_string_index(original.get("additional", {}).get("certificationsTraining", []), "additional.certificationsTraining")
    new_certs = _build_string_index(improved.get("additional", {}).get("certificationsTraining", []), "additional.certificationsTraining")
    for c in set(new_certs) - set(orig_certs):
        changes.append(ResumeFieldDiff(field_path="additional.certificationsTraining", field_type="certification", change_type="added", new_value=new_certs[c], confidence="high"))
    for c in set(orig_certs) - set(new_certs):
        changes.append(ResumeFieldDiff(field_path="additional.certificationsTraining", field_type="certification", change_type="removed", original_value=orig_certs[c], confidence="medium"))

    total = len(changes)
    skills_added = sum(1 for c in changes if c.field_type == "skill" and c.change_type == "added")
    skills_removed = sum(1 for c in changes if c.field_type == "skill" and c.change_type == "removed")
    desc_mod = sum(1 for c in changes if c.field_type == "description")
    certs_added = sum(1 for c in changes if c.field_type == "certification" and c.change_type == "added")
    high_risk = sum(1 for c in changes if c.confidence == "high")

    summary = ResumeDiffSummary(
        total_changes=total,
        skills_added=skills_added,
        skills_removed=skills_removed,
        descriptions_modified=desc_mod,
        certifications_added=certs_added,
        high_risk_changes=high_risk
    )
    return summary, changes