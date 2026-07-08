"""Database wrapper, LiteLLM wrapper, and resume tailoring/improvement core logic."""

import asyncio
import copy
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Callable
from uuid import uuid4
from difflib import SequenceMatcher
from dataclasses import dataclass

from tinydb import Query, TinyDB
from tinydb.table import Table
import litellm

from app.config import settings
from app.schemas import (
    ResumeData,
    ResumeFieldDiff,
    ResumeDiffSummary,
    ImprovementSuggestion,
    RefinementStats,
)

logger = logging.getLogger(__name__)

# ==========================================
# 1. DATABASE LAYER (TINYDB WRAPPER)
# ==========================================

class Database:
    """TinyDB wrapper for resume matcher data."""

    _master_resume_lock = asyncio.Lock()

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or settings.db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db: TinyDB | None = None

    @property
    def db(self) -> TinyDB:
        """Lazy initialization of TinyDB instance."""
        if self._db is None:
            self._db = TinyDB(self.db_path)
        return self._db

    @property
    def resumes(self) -> Table:
        return self.db.table("resumes")

    @property
    def jobs(self) -> Table:
        return self.db.table("jobs")

    @property
    def improvements(self) -> Table:
        return self.db.table("improvements")

    def close(self) -> None:
        if self._db is not None:
            self._db.close()
            self._db = None

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
    ) -> dict[str, Any]:
        resume_id = str(uuid4())
        now = datetime.now(timezone.utc).isoformat()

        doc = {
            "resume_id": resume_id,
            "content": content,
            "content_type": content_type,
            "filename": filename,
            "is_master": is_master,
            "parent_id": parent_id,
            "processed_data": processed_data,
            "processing_status": processing_status,
            "cover_letter": cover_letter,
            "outreach_message": outreach_message,
            "title": title,
            "created_at": now,
            "updated_at": now,
        }
        self.resumes.insert(doc)
        return doc

    async def create_resume_atomic_master(
        self,
        content: str,
        content_type: str = "md",
        filename: str | None = None,
        processed_data: dict[str, Any] | None = None,
        processing_status: str = "pending",
        cover_letter: str | None = None,
        outreach_message: str | None = None,
    ) -> dict[str, Any]:
        async with self._master_resume_lock:
            current_master = self.get_master_resume()
            is_master = current_master is None

            if current_master and current_master.get("processing_status") in ("failed", "processing"):
                Resume = Query()
                self.resumes.update(
                    {"is_master": False},
                    Resume.resume_id == current_master["resume_id"],
                )
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
            )

    def get_resume(self, resume_id: str) -> dict[str, Any] | None:
        Resume = Query()
        result = self.resumes.search(Resume.resume_id == resume_id)
        return result[0] if result else None

    def get_master_resume(self) -> dict[str, Any] | None:
        Resume = Query()
        result = self.resumes.search(Resume.is_master == True)
        return result[0] if result else None

    def update_resume(self, resume_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        Resume = Query()
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        updated_count = self.resumes.update(updates, Resume.resume_id == resume_id)

        if not updated_count:
            raise ValueError(f"Resume not found: {resume_id}")

        result = self.get_resume(resume_id)
        if not result:
            raise ValueError(f"Resume disappeared after update: {resume_id}")

        return result

    def delete_resume(self, resume_id: str) -> bool:
        Resume = Query()
        removed = self.resumes.remove(Resume.resume_id == resume_id)
        return len(removed) > 0

    def list_resumes(self) -> list[dict[str, Any]]:
        return list(self.resumes.all())

    def set_master_resume(self, resume_id: str) -> bool:
        Resume = Query()
        target = self.resumes.search(Resume.resume_id == resume_id)
        if not target:
            return False
        self.resumes.update({"is_master": False}, Resume.is_master == True)
        updated = self.resumes.update(
            {"is_master": True}, Resume.resume_id == resume_id
        )
        return len(updated) > 0

    def create_job(self, content: str, resume_id: str | None = None) -> dict[str, Any]:
        job_id = str(uuid4())
        now = datetime.now(timezone.utc).isoformat()

        doc = {
            "job_id": job_id,
            "content": content,
            "resume_id": resume_id,
            "created_at": now,
        }
        self.jobs.insert(doc)
        return doc

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        Job = Query()
        result = self.jobs.search(Job.job_id == job_id)
        return result[0] if result else None

    def update_job(self, job_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        Job = Query()
        updated = self.jobs.update(updates, Job.job_id == job_id)
        if not updated:
            return None
        return self.get_job(job_id)

    def create_improvement(
        self,
        original_resume_id: str,
        tailored_resume_id: str,
        job_id: str,
        improvements: list[dict[str, Any]],
    ) -> dict[str, Any]:
        request_id = str(uuid4())
        now = datetime.now(timezone.utc).isoformat()

        doc = {
            "request_id": request_id,
            "original_resume_id": original_resume_id,
            "tailored_resume_id": tailored_resume_id,
            "job_id": job_id,
            "improvements": improvements,
            "created_at": now,
        }
        self.improvements.insert(doc)
        return doc

    def get_improvement_by_tailored_resume(
        self, tailored_resume_id: str
    ) -> dict[str, Any] | None:
        Improvement = Query()
        result = self.improvements.search(
            Improvement.tailored_resume_id == tailored_resume_id
        )
        return result[0] if result else None

    def get_stats(self) -> dict[str, Any]:
        return {
            "total_resumes": len(self.resumes),
            "total_jobs": len(self.jobs),
            "total_improvements": len(self.improvements),
            "has_master_resume": self.get_master_resume() is not None,
        }

    def reset_database(self) -> None:
        self.resumes.truncate()
        self.jobs.truncate()
        self.improvements.truncate()


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

PARSE_RESUME_PROMPT = """Parse this resume into JSON. Output ONLY the JSON object, no other text.
Example format:
{schema}
Resume to parse:
{resume_text}"""

EXTRACT_KEYWORDS_PROMPT = """Extract job requirements as JSON. Output ONLY the JSON object, no other text.
Example format:
{{
  "required_skills": ["Python", "AWS"],
  "preferred_skills": ["Kubernetes"],
  "experience_requirements": ["5+ years"],
  "education_requirements": ["Bachelor's in CS"],
  "key_responsibilities": ["Lead team"],
  "keywords": ["microservices"],
  "experience_years": 5,
  "seniority_level": "senior"
}}
Job description:
{job_description}"""

CRITICAL_TRUTHFULNESS_RULES = """CRITICAL TRUTHFULNESS RULES - NEVER VIOLATE:
1. DO NOT add any skill, tool, technology, or certification that is not explicitly mentioned in the original resume
2. DO NOT invent numeric achievements (e.g., "increased by 30%") unless they exist in original
3. DO NOT add company names or employment dates not in original
4. Preserve factual accuracy - only use information provided by the candidate
"""

IMPROVE_RESUME_PROMPT_FULL = """Tailor this resume for the job. Output ONLY the JSON object, no other text.

{critical_truthfulness_rules}

Rules:
- Rephrase content to highlight relevant experience
- DO NOT invent new information
- Preserve original date ranges exactly - do not modify years
- Do NOT use em dash ("—") anywhere in the writing

Job Description:
{job_description}

Keywords to emphasize:
{job_keywords}

Original Resume:
{original_resume}

Output in this JSON format:
{schema}"""

GENERATE_TITLE_PROMPT = """Extract the job title and company name from this job description.
Format: "Role @ Company" (e.g., "Senior Frontend Engineer @ Stripe")
Job Description:
{job_description}
Output the title only, nothing else."""

# ==========================================
# 4. PARSING & IMPROVEMENT CORE LOGIC
# ==========================================

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
    return await complete_json(prompt, "You are a professional resume parser.")

async def extract_job_keywords(job_description: str) -> dict[str, Any]:
    sanitized = _sanitize_user_input(job_description)
    prompt = EXTRACT_KEYWORDS_PROMPT.format(job_description=sanitized)
    return await complete_json(prompt, "You are an expert job description analyzer.")

async def generate_job_title(job_description: str) -> str:
    sanitized = _sanitize_user_input(job_description)
    prompt = GENERATE_TITLE_PROMPT.format(job_description=sanitized)
    title = await complete(prompt, "You are a precise title parser.")
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
    result = await complete_json(prompt, "You are an expert resume editor. Output valid JSON.", max_tokens=8192)
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