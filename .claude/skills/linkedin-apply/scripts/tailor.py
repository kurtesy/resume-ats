#!/usr/bin/env python3
"""Tailor the master resume against a LinkedIn job description and save the PDF.

Two modes:

1. Full run (default):
       tailor.py --job-id <id> --jd-file <path> [--url U] [--title T] [--company C]
   Resolves the master resume, uploads the JD, runs /improve, and renders the
   tailored PDF. Writes job.txt + metadata.json *before* the PDF step so a
   PDF failure does not lose the tailored_resume_id.

2. PDF-only retry:
       tailor.py --job-id <id> --pdf-only
   Reads the existing metadata.json under the job-id folder and just downloads
   the PDF for the already-tailored resume. Use this after fixing whatever
   blocked the original PDF render (usually: frontend was down).

Output layout (apps/backend/data/linkedin/<job_id>/):
    resume.pdf         — tailored CV (only present when PDF render succeeded)
    job.txt            — raw JD
    metadata.json      — ids + source url + pdf_status
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API_BASE = os.environ.get("RESUME_MATCHER_API", "http://localhost:8000/api/v1")
FRONTEND_BASE = os.environ.get("RESUME_MATCHER_FRONTEND", "http://localhost:3000")
REPO_ROOT = Path(__file__).resolve().parents[4]
OUTPUT_ROOT = REPO_ROOT / "apps" / "backend" / "data" / "linkedin"


def _request(method: str, path: str, body: dict | None = None, raw: bool = False, timeout: int = 300):
    url = f"{API_BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = resp.read()
            return payload if raw else json.loads(payload)
    except urllib.error.HTTPError as e:
        sys.stderr.write(f"HTTP {e.code} {method} {url}\n{e.read().decode(errors='replace')}\n")
        raise


def _probe(url: str, timeout: int = 3) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return 200 <= resp.status < 500
    except Exception:
        return False


def preflight(require_frontend: bool) -> None:
    if not _probe(f"{API_BASE}/health"):
        raise SystemExit(
            f"Backend not reachable at {API_BASE}. Start it with: npm run dev:backend"
        )
    if require_frontend and not _probe(f"{FRONTEND_BASE}/"):
        raise SystemExit(
            f"Frontend not reachable at {FRONTEND_BASE}. PDF rendering needs it. "
            f"Start it with: npm run dev:frontend"
        )


def get_master_resume_id() -> str:
    resp = _request("GET", "/resumes/list?include_master=true")
    for r in resp.get("data", []):
        if r.get("is_master"):
            return r["resume_id"]
    raise SystemExit("No master resume found. Upload one via the app first.")


def upload_job(jd_text: str, resume_id: str) -> str:
    resp = _request(
        "POST",
        "/jobs/upload",
        {"job_descriptions": [jd_text], "resume_id": resume_id},
    )
    return resp["job_id"][0]


def improve(resume_id: str, job_id: str) -> tuple[str, dict]:
    """Tailor the resume and return (tailored_resume_id, data_dict).

    The data_dict includes `refinement_stats` with initial/final keyword
    match percentages — used by the caller for the ATS verification step.
    """
    resp = _request(
        "POST",
        "/resumes/improve",
        {"resume_id": resume_id, "job_id": job_id},
    )
    data = resp.get("data") or {}
    new_id = data.get("resume_id") or resp.get("resume_id")
    if not new_id:
        raise SystemExit(f"Improve did not return a resume_id: {resp}")
    return new_id, data


def extract_ats_report(data: dict) -> dict:
    """Pull the ATS-style match report out of an /improve response."""
    stats = data.get("refinement_stats") or {}
    return {
        "initial_match_percentage": stats.get("initial_match_percentage"),
        "final_match_percentage": stats.get("final_match_percentage"),
        "keywords_injected": stats.get("keywords_injected", 0),
        "passes_completed": stats.get("passes_completed", 0),
        "alignment_violations_fixed": stats.get("alignment_violations_fixed", 0),
        "ai_phrases_removed": stats.get("ai_phrases_removed", []),
        "refinement_attempted": data.get("refinement_attempted", False),
        "refinement_successful": data.get("refinement_successful", False),
        "warnings": data.get("warnings", []),
    }


def download_pdf(resume_id: str) -> bytes:
    return _request("GET", f"/resumes/{resume_id}/pdf", raw=True)


def _write_metadata(out_dir: Path, meta: dict) -> None:
    (out_dir / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")


def _load_metadata(out_dir: Path) -> dict:
    path = out_dir / "metadata.json"
    if not path.exists():
        raise SystemExit(f"No metadata.json at {path}. Run a full tailor first.")
    return json.loads(path.read_text(encoding="utf-8"))


def run_full(args: argparse.Namespace, out_dir: Path) -> int:
    jd_path = Path(args.jd_file)
    if not jd_path.exists():
        raise SystemExit(f"JD file not found: {jd_path}")
    jd_text = jd_path.read_text(encoding="utf-8").strip()
    if not jd_text:
        raise SystemExit("JD file is empty")

    print("[1/4] Resolving master resume...", flush=True)
    master_id = get_master_resume_id()

    print("[2/4] Uploading job description...", flush=True)
    backend_job_id = upload_job(jd_text, master_id)

    print("[3/4] Tailoring resume (this can take 30-60s)...", flush=True)
    tailored_id, improve_data = improve(master_id, backend_job_id)
    ats = extract_ats_report(improve_data)

    # Persist JD + metadata BEFORE the PDF step so a PDF failure does not
    # waste the LLM call — a later --pdf-only run can pick up tailored_id.
    (out_dir / "job.txt").write_text(jd_text, encoding="utf-8")
    meta = {
        "linkedin_job_id": args.job_id,
        "linkedin_url": args.url,
        "job_title": args.title,
        "company": args.company,
        "master_resume_id": master_id,
        "backend_job_id": backend_job_id,
        "tailored_resume_id": tailored_id,
        "ats_report": ats,
        "pdf_status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_metadata(out_dir, meta)
    _print_ats_report(ats)

    print("[4/4] Downloading PDF...", flush=True)
    try:
        pdf_bytes = download_pdf(tailored_id)
    except urllib.error.HTTPError as e:
        meta["pdf_status"] = f"failed: HTTP {e.code} — run with --pdf-only to retry"
        _write_metadata(out_dir, meta)
        print(
            f"\nTailoring succeeded (tailored_resume_id={tailored_id}) but PDF render failed.\n"
            f"job.txt and metadata.json were saved. Once the cause is fixed, retry just the PDF:\n"
            f"  python3 {sys.argv[0]} --job-id {args.job_id} --pdf-only",
            file=sys.stderr,
        )
        return 2

    (out_dir / "resume.pdf").write_bytes(pdf_bytes)
    meta["pdf_status"] = "ok"
    _write_metadata(out_dir, meta)
    _print_summary(out_dir, meta)
    return 0


def run_pdf_only(args: argparse.Namespace, out_dir: Path) -> int:
    meta = _load_metadata(out_dir)
    tailored_id = meta.get("tailored_resume_id")
    if not tailored_id:
        raise SystemExit("metadata.json has no tailored_resume_id — re-run a full tailor.")
    print(f"Downloading PDF for tailored_resume_id={tailored_id}...", flush=True)
    pdf_bytes = download_pdf(tailored_id)
    (out_dir / "resume.pdf").write_bytes(pdf_bytes)
    meta["pdf_status"] = "ok"
    _write_metadata(out_dir, meta)
    _print_summary(out_dir, meta)
    return 0


def _print_ats_report(ats: dict) -> None:
    initial = ats.get("initial_match_percentage")
    final = ats.get("final_match_percentage")
    print("\n=== ATS keyword match ===", flush=True)
    if final is None:
        print("  (no refinement_stats in /improve response — backend may have skipped refinement)")
        for w in ats.get("warnings", []):
            print(f"  warning: {w}")
        return
    init_str = f"{initial:.1f}%" if initial is not None else "n/a"
    delta = (final - initial) if (initial is not None) else None
    delta_str = f" (Δ {delta:+.1f})" if delta is not None else ""
    print(f"  before refinement: {init_str}")
    print(f"  after  refinement: {final:.1f}%{delta_str}")
    print(f"  keywords injected:  {ats.get('keywords_injected', 0)}")
    print(f"  refinement passes:  {ats.get('passes_completed', 0)}")
    if ats.get("alignment_violations_fixed"):
        print(f"  alignment fixes:    {ats['alignment_violations_fixed']}")
    if ats.get("ai_phrases_removed"):
        print(f"  AI phrases removed: {len(ats['ai_phrases_removed'])}")
    for w in ats.get("warnings", []):
        print(f"  warning: {w}")


def _print_summary(out_dir: Path, meta: dict) -> None:
    print(f"\nSaved to: {out_dir}")
    print(f"  - resume.pdf       (tailored CV)")
    print(f"  - job.txt          (raw JD)")
    print(f"  - metadata.json    (ids + source url + ats_report)")
    print(f"\ntailored_resume_id: {meta.get('tailored_resume_id')}")
    print(f"Edit in UI: {FRONTEND_BASE}/tailor/{meta.get('tailored_resume_id')}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--job-id", required=True, help="LinkedIn job ID (used as folder name)")
    ap.add_argument("--jd-file", help="Path to a text file containing the JD (full run only)")
    ap.add_argument("--url", default=None)
    ap.add_argument("--title", default=None)
    ap.add_argument("--company", default=None)
    ap.add_argument(
        "--pdf-only",
        action="store_true",
        help="Skip tailoring; just download the PDF for the existing metadata.json",
    )
    args = ap.parse_args()

    out_dir = OUTPUT_ROOT / args.job_id
    out_dir.mkdir(parents=True, exist_ok=True)

    preflight(require_frontend=True)

    if args.pdf_only:
        return run_pdf_only(args, out_dir)

    if not args.jd_file:
        ap.error("--jd-file is required unless --pdf-only is set")
    return run_full(args, out_dir)


if __name__ == "__main__":
    sys.exit(main())
