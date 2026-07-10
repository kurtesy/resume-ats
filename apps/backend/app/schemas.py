"""Pydantic schemas for Resume Matcher."""

import copy
import re
from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator

_TEXT_VALUE_KEYS = ("text", "summary", "description", "value", "content", "title", "subtitle", "name", "label")
_BULLET_PREFIX_RE = re.compile(r"^\s*(?:[-*•]+|\d+[.)])\s*")

def _extract_text_fragments(value: Any, depth: int = 0, max_depth: int = 10) -> list[str]:
    if depth >= max_depth or value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    if isinstance(value, (int, float)):
        return [str(value)]
    if isinstance(value, list):
        fragments = []
        for item in value:
            fragments.extend(_extract_text_fragments(item, depth + 1, max_depth))
        return fragments
    if isinstance(value, dict):
        fragments = []
        for key in _TEXT_VALUE_KEYS:
            if key in value:
                fragments.extend(_extract_text_fragments(value.get(key), depth + 1, max_depth))
        if fragments:
            return fragments
        for nested in value.values():
            fragments.extend(_extract_text_fragments(nested, depth + 1, max_depth))
        return fragments
    return []

def _coerce_text(value: Any, joiner: str = " ") -> str:
    return joiner.join(_extract_text_fragments(value)).strip()

def _coerce_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = _coerce_text(value)
    return text or None

def _split_description_lines(value: str) -> list[str]:
    items = []
    for raw_line in re.split(r"\r?\n+", value):
        line = _BULLET_PREFIX_RE.sub("", raw_line.strip())
        if line:
            items.append(line)
    return items

def _coerce_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return _split_description_lines(value)
    if isinstance(value, list):
        items = []
        for entry in value:
            if isinstance(entry, str):
                items.extend(_split_description_lines(entry))
                continue
            coerced = _coerce_text(entry)
            if coerced:
                items.append(coerced)
        return items
    coerced = _coerce_text(value)
    return [coerced] if coerced else []

class SectionType(str, Enum):
    PERSONAL_INFO = "personalInfo"
    TEXT = "text"
    ITEM_LIST = "itemList"
    STRING_LIST = "stringList"

class PersonalInfo(BaseModel):
    name: str = ""
    title: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    website: str | None = None
    linkedin: str | None = None
    github: str | None = None

class Experience(BaseModel):
    id: int = 0
    title: str = ""
    company: str = ""
    location: str | None = None
    years: str | None = ""
    description: list[str] = Field(default_factory=list)

    @field_validator("description", mode="before")
    @classmethod
    def _normalize_description(cls, value: Any) -> list[str]:
        return _coerce_string_list(value)

class Education(BaseModel):
    id: int = 0
    institution: str = ""
    degree: str = ""
    years: str | None = ""
    description: str | None = None

    @field_validator("description", mode="before")
    @classmethod
    def _normalize_description(cls, value: Any) -> str | None:
        return _coerce_optional_text(value)

class Project(BaseModel):
    id: int = 0
    name: str = ""
    role: str = ""
    years: str | None = ""
    github: str | None = None
    website: str | None = None
    description: list[str] = Field(default_factory=list)

    @field_validator("description", mode="before")
    @classmethod
    def _normalize_description(cls, value: Any) -> list[str]:
        return _coerce_string_list(value)

class AdditionalInfo(BaseModel):
    technicalSkills: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    certificationsTraining: list[str] = Field(default_factory=list)
    awards: list[str] = Field(default_factory=list)

    @field_validator("technicalSkills", "languages", "certificationsTraining", "awards", mode="before")
    @classmethod
    def _normalize_string_fields(cls, value: Any) -> list[str]:
        return _coerce_string_list(value)

class SectionMeta(BaseModel):
    id: str
    key: str
    displayName: str
    sectionType: SectionType
    isDefault: bool = True
    isVisible: bool = True
    order: int = 0

class CustomSectionItem(BaseModel):
    id: int = 0
    title: str = ""
    subtitle: str | None = None
    location: str | None = None
    years: str | None = ""
    description: list[str] = Field(default_factory=list)

    @field_validator("description", mode="before")
    @classmethod
    def _normalize_description(cls, value: Any) -> list[str]:
        return _coerce_string_list(value)

class CustomSection(BaseModel):
    sectionType: SectionType
    items: list[CustomSectionItem] | None = None
    strings: list[str] | None = None
    text: str | None = None

    @field_validator("strings", mode="before")
    @classmethod
    def _normalize_strings(cls, value: Any) -> list[str] | None:
        if value is None:
            return None
        return _coerce_string_list(value)

    @field_validator("text", mode="before")
    @classmethod
    def _normalize_text(cls, value: Any) -> str | None:
        return _coerce_optional_text(value)

DEFAULT_SECTION_META = [
    {"id": "personalInfo", "key": "personalInfo", "displayName": "Personal Info", "sectionType": SectionType.PERSONAL_INFO, "isDefault": True, "isVisible": True, "order": 0},
    {"id": "summary", "key": "summary", "displayName": "Summary", "sectionType": SectionType.TEXT, "isDefault": True, "isVisible": True, "order": 1},
    {"id": "workExperience", "key": "workExperience", "displayName": "Experience", "sectionType": SectionType.ITEM_LIST, "isDefault": True, "isVisible": True, "order": 2},
    {"id": "education", "key": "education", "displayName": "Education", "sectionType": SectionType.ITEM_LIST, "isDefault": True, "isVisible": True, "order": 3},
    {"id": "personalProjects", "key": "personalProjects", "displayName": "Projects", "sectionType": SectionType.ITEM_LIST, "isDefault": True, "isVisible": True, "order": 4},
    {"id": "additional", "key": "additional", "displayName": "Skills & Awards", "sectionType": SectionType.STRING_LIST, "isDefault": True, "isVisible": True, "order": 5},
]

class ResumeData(BaseModel):
    personalInfo: PersonalInfo = Field(default_factory=PersonalInfo)
    summary: str = ""
    workExperience: list[Experience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    personalProjects: list[Project] = Field(default_factory=list)
    additional: AdditionalInfo = Field(default_factory=AdditionalInfo)
    sectionMeta: list[SectionMeta] = Field(default_factory=list)
    customSections: dict[str, Any] = Field(default_factory=dict)

    @field_validator("summary", mode="before")
    @classmethod
    def _normalize_summary(cls, value: Any) -> str:
        return _coerce_text(value)

def normalize_resume_data(data: dict[str, Any]) -> dict[str, Any]:
    if not data.get("sectionMeta"):
        data["sectionMeta"] = copy.deepcopy(DEFAULT_SECTION_META)
    if "customSections" not in data:
        data["customSections"] = {}
    return data

class ResumeUploadResponse(BaseModel):
    message: str
    request_id: str
    resume_id: str
    processing_status: Literal["pending", "processing", "ready", "failed"] = "pending"
    is_master: bool = False

class RawResume(BaseModel):
    id: int | None = None
    content: str
    content_type: str = "md"
    created_at: str
    processing_status: str = "pending"

class ResumeFetchData(BaseModel):
    resume_id: str
    raw_resume: RawResume
    processed_resume: ResumeData | None = None
    cover_letter: str | None = None
    outreach_message: str | None = None
    parent_id: str | None = None
    title: str | None = None

class ResumeFetchResponse(BaseModel):
    request_id: str
    data: ResumeFetchData

class ResumeSummary(BaseModel):
    resume_id: str
    filename: str | None = None
    is_master: bool = False
    parent_id: str | None = None
    processing_status: str = "pending"
    created_at: str
    updated_at: str
    title: str | None = None

class ResumeListResponse(BaseModel):
    request_id: str
    data: list[ResumeSummary]

class JobUploadRequest(BaseModel):
    job_descriptions: list[str]
    resume_id: str | None = None

class JobUploadResponse(BaseModel):
    message: str
    job_id: list[str]
    request: dict[str, Any]

class ImproveResumeRequest(BaseModel):
    resume_id: str
    job_id: str
    prompt_id: str | None = None

class ImprovementSuggestion(BaseModel):
    suggestion: str
    lineNumber: int | None = None

class ResumeFieldDiff(BaseModel):
    field_path: str
    field_type: Literal["skill", "description", "summary", "certification", "experience", "education", "project"]
    change_type: Literal["added", "removed", "modified"]
    original_value: str | None = None
    new_value: str | None = None
    confidence: Literal["low", "medium", "high"] = "medium"

class ResumeDiffSummary(BaseModel):
    total_changes: int
    skills_added: int
    skills_removed: int
    descriptions_modified: int
    certifications_added: int
    high_risk_changes: int

class RefinementStats(BaseModel):
    passes_completed: int = 0
    keywords_injected: int = 0
    ai_phrases_removed: list[str] = Field(default_factory=list)
    alignment_violations_fixed: int = 0
    initial_match_percentage: float = 0.0
    final_match_percentage: float = 0.0

class ImproveResumeData(BaseModel):
    request_id: str
    resume_id: str | None = None
    job_id: str
    resume_preview: ResumeData
    improvements: list[ImprovementSuggestion]
    markdownOriginal: str | None = None
    markdownImproved: str | None = None
    cover_letter: str | None = None
    outreach_message: str | None = None
    diff_summary: ResumeDiffSummary | None = None
    detailed_changes: list[ResumeFieldDiff] | None = None
    refinement_stats: RefinementStats | None = None
    warnings: list[str] = Field(default_factory=list)
    refinement_attempted: bool = False
    refinement_successful: bool = False

class ImproveResumeResponse(BaseModel):
    request_id: str
    data: ImproveResumeData

class ImproveResumeConfirmRequest(BaseModel):
    resume_id: str
    job_id: str
    improved_data: ResumeData
    improvements: list[ImprovementSuggestion]

class LLMConfigRequest(BaseModel):
    provider: str | None = None
    model: str | None = None
    api_key: str | None = None
    api_base: str | None = None

class LLMConfigResponse(BaseModel):
    provider: str
    model: str
    api_key: str
    api_base: str | None = None

class FeatureConfigRequest(BaseModel):
    enable_cover_letter: bool | None = None
    enable_outreach_message: bool | None = None

class FeatureConfigResponse(BaseModel):
    enable_cover_letter: bool = False
    enable_outreach_message: bool = False

class LanguageConfigRequest(BaseModel):
    ui_language: str | None = None
    content_language: str | None = None

class LanguageConfigResponse(BaseModel):
    ui_language: str = "en"
    content_language: str = "en"
    supported_languages: list[str] = ["en"]

class PromptOption(BaseModel):
    id: str
    label: str
    description: str

class PromptConfigRequest(BaseModel):
    default_prompt_id: str | None = None

class PromptConfigResponse(BaseModel):
    default_prompt_id: str
    prompt_options: list[PromptOption]

class ApiKeyProviderStatus(BaseModel):
    provider: str
    configured: bool
    masked_key: str | None = None

class ApiKeyStatusResponse(BaseModel):
    providers: list[ApiKeyProviderStatus]

class ApiKeysUpdateRequest(BaseModel):
    openai: str | None = None
    anthropic: str | None = None
    google: str | None = None
    openrouter: str | None = None
    deepseek: str | None = None

class ApiKeysUpdateResponse(BaseModel):
    message: str
    updated_providers: list[str]

class UpdateCoverLetterRequest(BaseModel):
    content: str

class UpdateOutreachMessageRequest(BaseModel):
    content: str

class UpdateTitleRequest(BaseModel):
    title: str

class ResetDatabaseRequest(BaseModel):
    confirm: str | None = None

class GenerateContentResponse(BaseModel):
    content: str
    message: str

class HealthResponse(BaseModel):
    status: str
    llm: dict[str, Any]

class StatusResponse(BaseModel):
    status: str
    llm_configured: bool
    llm_healthy: bool
    has_master_resume: bool
    database_stats: dict[str, Any]

class ScrapeJobRequest(BaseModel):
    url: str

class ScrapeJobResponse(BaseModel):
    description: str

class EnrichmentItem(BaseModel):
    item_id: str
    item_type: str
    title: str
    subtitle: str | None = None
    current_description: list[str] = Field(default_factory=list)
    weakness_reason: str

class EnrichmentQuestion(BaseModel):
    question_id: str
    item_id: str
    question: str
    placeholder: str = ""

class AnalysisResponse(BaseModel):
    items_to_enrich: list[EnrichmentItem] = Field(default_factory=list)
    questions: list[EnrichmentQuestion] = Field(default_factory=list)
    analysis_summary: str | None = None

class AnswerInput(BaseModel):
    question_id: str
    answer: str

class EnhanceRequest(BaseModel):
    resume_id: str
    answers: list[AnswerInput]

class EnhancedDescription(BaseModel):
    item_id: str
    item_type: str
    title: str
    original_description: list[str] = Field(default_factory=list)
    enhanced_description: list[str] = Field(default_factory=list)

class EnhancementPreview(BaseModel):
    enhancements: list[EnhancedDescription] = Field(default_factory=list)

class RegenerateItemInput(BaseModel):
    item_id: str
    item_type: str
    title: str
    subtitle: str | None = None
    current_content: list[str] = Field(default_factory=list)

class RegenerateRequest(BaseModel):
    resume_id: str
    items: list[RegenerateItemInput]
    instruction: str
    output_language: str = "en"

class RegeneratedItem(BaseModel):
    item_id: str
    item_type: str
    title: str
    subtitle: str | None = None
    original_content: list[str] = Field(default_factory=list)
    new_content: list[str] = Field(default_factory=list)
    diff_summary: str = ""

class RegenerateItemError(BaseModel):
    item_id: str
    item_type: str
    title: str
    subtitle: str | None = None
    message: str

class RegenerateResponse(BaseModel):
    regenerated_items: list[RegeneratedItem] = Field(default_factory=list)
    errors: list[RegenerateItemError] = Field(default_factory=list)