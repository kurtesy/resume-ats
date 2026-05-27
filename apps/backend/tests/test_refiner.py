"""Tests for the refinement pipeline.

Locks in the fixes for the keyword-match regression where post-refinement
score was lower than pre-refinement score because:

- AI-phrase removal stripped words the JD actually required ("scalable").
- Fabrication check used exact set difference, so "PostgreSQL 14" was
  flagged when master only had "PostgreSQL".
- No re-injection pass ran after alignment removed content containing JD
  keywords.
- Em-dashes had no replacement and were silently deleted (defensive guard).
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.prompts.refinement import AI_PHRASE_BLACKLIST, AI_PHRASE_REPLACEMENTS
from app.schemas.refinement import RefinementConfig
from app.services import refiner
from app.services.refiner import (
    _build_jd_keyword_guard,
    _is_essentially_in_master,
    _normalize_skill,
    refine_resume,
    remove_ai_phrases,
    validate_master_alignment,
)


# ---------------------------------------------------------------------------
# remove_ai_phrases: JD-keyword guard
# ---------------------------------------------------------------------------


def test_remove_ai_phrases_skips_jd_keywords() -> None:
    """The Flix regression: 'scalable' is blacklisted AND in the JD keywords.

    With the guard, it must survive removal.
    """
    data = {
        "summary": "Built scalable Python services and architected event pipelines.",
    }
    guard = _build_jd_keyword_guard({"required_skills": ["Python", "Scalable"]})

    cleaned, removed = remove_ai_phrases(data, guard)

    assert "scalable" in cleaned["summary"].lower()
    assert "scalable" not in {r.lower() for r in removed}
    # Non-guarded blacklist words still get replaced.
    assert "architected" not in cleaned["summary"].lower()


def test_remove_ai_phrases_without_guard_strips_everything() -> None:
    """Default behavior (no guard) still removes blacklist words."""
    data = {"summary": "Spearheaded a scalable platform."}
    cleaned, removed = remove_ai_phrases(data)
    assert "spearheaded" not in cleaned["summary"].lower()
    assert "scalable" not in cleaned["summary"].lower()
    assert {"spearheaded", "scalable"}.issubset({r.lower() for r in removed})


# ---------------------------------------------------------------------------
# Em-dash defensive guard
# ---------------------------------------------------------------------------


def test_em_dash_has_non_empty_replacement() -> None:
    """Em-dash and double/triple hyphen must map to a non-empty replacement.

    Otherwise punctuation is silently deleted and phrasing breaks.
    """
    for phrase in ("—", "---", "--"):
        assert phrase in AI_PHRASE_BLACKLIST, f"{phrase!r} dropped from blacklist"
        replacement = AI_PHRASE_REPLACEMENTS.get(phrase.lower(), "")
        assert replacement.strip(), f"{phrase!r} has empty replacement"


# ---------------------------------------------------------------------------
# validate_master_alignment: fuzzy fabrication check
# ---------------------------------------------------------------------------


def _resume_with_skills(skills: list[str]) -> dict[str, Any]:
    return {"additional": {"technicalSkills": skills}}


def _resume_with_certs(certs: list[str]) -> dict[str, Any]:
    return {"additional": {"certificationsTraining": certs}}


def test_fuzzy_skill_match_accepts_versioned_variant() -> None:
    """'PostgreSQL 14' must not be flagged when master has 'PostgreSQL'."""
    tailored = _resume_with_skills(["PostgreSQL 14", "Python 3.13"])
    master = _resume_with_skills(["PostgreSQL", "Python"])
    report = validate_master_alignment(tailored, master)
    fabricated = [v for v in report.violations if v.violation_type == "fabricated_skill"]
    assert fabricated == []
    assert report.is_aligned


def test_genuine_fabricated_skill_still_flagged() -> None:
    """Skill the master doesn't have at all is still a critical violation."""
    tailored = _resume_with_skills(["Python", "Rust"])
    master = _resume_with_skills(["Python"])
    report = validate_master_alignment(tailored, master)
    fabricated = [v for v in report.violations if v.violation_type == "fabricated_skill"]
    assert [v.value for v in fabricated] == ["rust"]
    assert not report.is_aligned


def test_fuzzy_cert_match_accepts_versioned_variant() -> None:
    tailored = _resume_with_certs(["AWS Certified Solutions Architect 2023"])
    master = _resume_with_certs(["AWS Certified Solutions Architect"])
    report = validate_master_alignment(tailored, master)
    fabricated = [v for v in report.violations if v.violation_type == "fabricated_cert"]
    assert fabricated == []


def test_fabricated_company_still_flagged_strictly() -> None:
    """Company integrity guard must remain strict — no fuzzy match here."""
    tailored = {
        "workExperience": [
            {"company": "Acme Corp", "title": "Engineer", "description": []},
            {"company": "FakeCo", "title": "Engineer", "description": []},
        ]
    }
    master = {"workExperience": [{"company": "Acme Corp", "title": "Engineer", "description": []}]}
    report = validate_master_alignment(tailored, master)
    fabricated_co = [v for v in report.violations if v.violation_type == "fabricated_company"]
    assert [v.value for v in fabricated_co] == ["fakeco"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def test_normalize_skill_strips_version_and_whitespace() -> None:
    assert _normalize_skill("PostgreSQL 14") == "postgresql"
    assert _normalize_skill("Python  3.13.1") == "python"
    assert _normalize_skill("AWS  S3 ") == "aws s3"
    assert _normalize_skill("") == ""


def test_is_essentially_in_master_substring_match() -> None:
    master = {"postgresql", "python", "aws"}
    assert _is_essentially_in_master("PostgreSQL 14", master)
    assert _is_essentially_in_master("AWS Lambda", master)  # tailored contains master
    assert _is_essentially_in_master("aws", master)  # exact
    assert not _is_essentially_in_master("Rust", master)


# ---------------------------------------------------------------------------
# refine_resume: regression — final score must be >= initial when JD keywords
# only appear in a fabricated bullet that gets removed
# ---------------------------------------------------------------------------


def test_refine_resume_does_not_drop_score_when_keyword_survives_in_master(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Initial tailored mentions Kafka in a fabricated bullet at FakeCo.

    Master has Kafka in real experience. Alignment removes the FakeCo entry,
    which initially drops the Kafka mention; the re-injection pass should
    notice Kafka is now missing and inject it back from master, restoring
    the score.
    """
    job_keywords = {
        "required_skills": ["Kafka", "Python"],
        "preferred_skills": [],
        "keywords": [],
    }
    master = {
        "additional": {"technicalSkills": ["Python", "Kafka"]},
        "workExperience": [
            {
                "company": "Acme Corp",
                "title": "Engineer",
                "description": ["Built Kafka event pipelines in Python."],
            }
        ],
    }
    initial_tailored = {
        "additional": {"technicalSkills": ["Python", "Kafka"]},
        "workExperience": [
            {
                "company": "Acme Corp",
                "title": "Engineer",
                "description": ["Built Python services."],
            },
            {
                "company": "FakeCo",  # fabricated — will be removed
                "title": "Engineer",
                "description": ["Built Kafka event pipelines."],
            },
        ],
    }

    async def fake_inject(
        tailored: dict[str, Any],
        keywords_to_inject: list[str],
        master_data: dict[str, Any],
        jd: str,
    ) -> dict[str, Any]:
        # Stand-in for the LLM call: append each missing keyword to the first
        # real work experience description, grounded in master.
        out = {**tailored}
        out["workExperience"] = [dict(e) for e in tailored.get("workExperience", [])]
        if out["workExperience"]:
            desc = list(out["workExperience"][0].get("description") or [])
            for kw in keywords_to_inject:
                desc.append(f"Used {kw} extensively (from master).")
            out["workExperience"][0]["description"] = desc
        return out

    monkeypatch.setattr(refiner, "inject_keywords", fake_inject)

    initial_match = refiner.calculate_keyword_match(initial_tailored, job_keywords)
    result = asyncio.run(
        refine_resume(
            initial_tailored=initial_tailored,
            master_resume=master,
            job_description="We need Python and Kafka.",
            job_keywords=job_keywords,
            config=RefinementConfig(),
        )
    )

    assert result.final_match_percentage >= initial_match, (
        f"Refinement lowered score: {initial_match} -> {result.final_match_percentage}"
    )
    # The fabricated company must have been removed.
    companies = [e["company"] for e in result.refined_data["workExperience"]]
    assert "FakeCo" not in companies
