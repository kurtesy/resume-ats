---
name: linkedin-apply
description: Tailor the master CV against a LinkedIn job posting. Drives Chrome via the chrome-devtools MCP to read the job description, then calls Resume Matcher backend APIs to upload the JD, run the /improve pipeline, and save the tailored PDF to apps/backend/data/linkedin/<linkedin_job_id>/. Use when the user gives a LinkedIn job URL and asks to apply / tailor / save a CV.
---

# LinkedIn Job Apply Agent

End-to-end flow: **Chrome MCP scrapes JD → backend tailors resume → PDF saved by LinkedIn job ID**.

The agent does **not** click Apply. It only produces the tailored PDF and metadata so the user can review and submit manually.

## Preconditions (check ALL of these before doing anything else)

The script's `preflight()` enforces 1 and 2, but check them up front so you can give the user one consolidated message if anything is missing — don't make them iterate.

1. **Backend on `:8000`** — `curl -fsS http://localhost:8000/api/v1/health`. If it fails: `npm run dev:backend`.

2. **Frontend on `:3000`** — `curl -fsS -o /dev/null http://localhost:3000/`. The backend's PDF renderer drives headless Chromium against `localhost:3000/print/...`, so without the frontend the tailoring succeeds but the PDF step returns 503. If down: `npm run dev:frontend`. **This was the #1 failure mode in past runs.**

3. **A master resume exists** — the script fails fast if not. Tell the user to upload one in the app.

4. **`chrome-devtools` MCP tools available** — if `mcp__chrome-devtools__*` isn't in the current tool list, stop and tell the user to install/enable the server. You can offer the paste-JD fallback (see below) as a workaround.

## Inputs

A LinkedIn job URL, e.g.
- `https://www.linkedin.com/jobs/view/4012345678/`
- `https://www.linkedin.com/jobs/collections/recommended/?currentJobId=4012345678`

The numeric **LinkedIn job ID** is what gets used as the output folder name. Extract it from the URL path (`/jobs/view/<id>/`) or `currentJobId` query param.

## Steps

### 1. Open the job in Chrome and capture the JD

```
mcp__chrome-devtools__new_page url=<canonical /jobs/view/<id>/ URL>
mcp__chrome-devtools__wait_for text=["About the job", "Job description", "Apply"]
```

**Authwall detection.** If the resulting page URL contains `/authwall` or `/login`, or `wait_for` times out: the MCP's *isolated* Chromium has no LinkedIn session. (The MCP launches its own Chrome — it does NOT inherit cookies from the user's normal Chrome.) Two options:

  - **Recommended one-time fix:** ask the user to manually sign into LinkedIn *in the Chromium window the MCP just opened* (not their normal Chrome). The session cookie persists across MCP runs.
  - **Bypass:** ask the user to paste the JD text directly — skip to step 2 with their pasted text and `--url` set to the LinkedIn URL. Title/company are nice-to-have, not required.

### 2. Extract the JD text

LinkedIn renames CSS classes frequently — the old `.jobs-description-content__text` selector did NOT work in the last test. Use a **heading-based extraction** as the primary path:

```javascript
() => {
  const headings = Array.from(document.querySelectorAll('h2'));
  const aboutH = headings.find(h => /about the job/i.test(h.innerText));
  let jd = null;
  if (aboutH) {
    let el = aboutH.nextElementSibling;
    while (el && (!el.innerText || el.innerText.trim().length < 100)) el = el.nextElementSibling;
    if (el) jd = el.innerText.trim();
  }
  if (!jd) {
    // Fallback: largest element on the page that mentions both "about the job" and a section header
    const all = Array.from(document.querySelectorAll('div, section, article'));
    const big = all.map(e => ({ e, t: (e.innerText || '').trim() }))
      .filter(x => x.t.length > 500 && /about the job|about the role|about you/i.test(x.t))
      .sort((a, b) => a.t.length - b.t.length)[0];
    if (big) jd = big.t;
  }
  const titleEl = document.querySelector('h1');
  const compEl = document.querySelector('a[href*="/company/"]');
  return {
    jd_len: jd ? jd.length : 0,
    jd,
    title: titleEl?.innerText.trim() || null,
    company: compEl?.innerText.trim() || null,
  };
}
```

If `jd_len < 500`: the snapshot probably has the text but the script missed it. Read the page snapshot from `take_snapshot` (or the most recent `wait_for` response) and reconstruct the JD from `StaticText` nodes under the `"About the job"` heading. Don't fabricate — only use text that actually appeared in the snapshot.

### 3. Write the JD to a temp file

LinkedIn JDs can be many KB. Use the `Write` tool to save the text to `/tmp/linkedin-jd-<job_id>.txt`. Don't pass it through argv.

### 4. Run the tailor script

```bash
python3 .claude/skills/linkedin-apply/scripts/tailor.py \
  --job-id <linkedin_job_id> \
  --jd-file /tmp/linkedin-jd-<job_id>.txt \
  --url "<linkedin_url>" \
  --title "<job_title>" \
  --company "<company>"
```

The script:
1. Pre-flights `:8000` and `:3000`. Fails fast with the exact command to start the missing one.
2. Resolves the master `resume_id`.
3. `POST /jobs/upload` with the JD text.
4. `POST /resumes/improve` to tailor (slow step, ~30–60s).
5. **Extracts the ATS keyword-match report** from `data.refinement_stats` in the `/improve` response — `initial_match_percentage`, `final_match_percentage`, keywords injected, refinement passes. No second API call; the backend's multi-pass refiner already computes these.
6. Writes `job.txt` + `metadata.json` (with `ats_report` and `pdf_status: "pending"`) **before** the PDF call, so a PDF failure does not lose the tailored_resume_id or the match score.
7. Prints the ATS report to stdout (see step 6 of the user-facing flow).
8. `GET /resumes/{tailored_id}/pdf`, saves `resume.pdf`, updates `pdf_status: "ok"`.

Exit codes: `0` = full success, `2` = tailored but PDF failed (metadata persisted), other non-zero = something earlier failed.

### 5. PDF-only retry

If the PDF step failed (exit 2), don't re-tailor — that wastes the LLM call. After fixing the cause (almost always: start the frontend), run:

```bash
python3 .claude/skills/linkedin-apply/scripts/tailor.py --job-id <linkedin_job_id> --pdf-only
```

This reads the existing `metadata.json`, downloads the PDF for the already-tailored resume, and updates `pdf_status`.

### 6. Report back (include the ATS check)

Show the user:
- Path to `resume.pdf`
- **ATS keyword match**: `before → after` and the delta. The script prints this; also pluck it from `metadata.json` (`ats_report.initial_match_percentage` → `ats_report.final_match_percentage`).
  - If `final_match_percentage >= 75` — call it a good match.
  - If `50 ≤ final < 75` — acceptable; flag that the user may want to manually inject 1–2 missing keywords via the UI before submitting.
  - If `final < 50` — warn the user: the master CV may not be a good fit for this role, or the JD scrape missed structured sections. Suggest reviewing in the UI before applying.
  - If `ats_report.final_match_percentage` is `null` — refinement was skipped (no master resume to align against, or backend warning). Surface any items in `ats_report.warnings`.
- `tailored_resume_id` and the UI link: `http://localhost:3000/tailor/<tailored_resume_id>`
- A reminder that Easy Apply was **not** submitted

## Environment overrides

- `RESUME_MATCHER_API` — defaults to `http://localhost:8000/api/v1`
- `RESUME_MATCHER_FRONTEND` — defaults to `http://localhost:3000`

## Idempotency

Re-running a full tailor on the same `<job_id>` overwrites the files in that folder. That's intentional — the user might re-tailor after editing the master CV. Use `--pdf-only` when you only need to redo the PDF (no LLM call).

## What NOT to do

- Don't `click` the Apply / Easy Apply button. Out of scope and risks LinkedIn flagging the account.
- Don't try to parse the LinkedIn JD HTML in Python — let the browser hand you rendered text.
- Don't add a new backend endpoint for this.
- Don't re-tailor when only the PDF failed — `--pdf-only` exists for exactly that case.
