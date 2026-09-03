# Vercel FastAPI Deployment Guide

This guide explains how Resume Matcher's FastAPI backend runs on Vercel's serverless Python functions.

## Architecture

```
Vercel Edge → Python@3.13 Serverless Function → api/index.py → FastAPI ASGI app
```

### How It Works

1. **vercel.json** — Configuration file that tells Vercel:
   - Routing: Map all paths to `api/index.py` using standard rewrites
   - Environment: Set PYTHONUNBUFFERED=1 for clean real-time logs
   - Zero-Config Dependencies: Vercel automatically detects `requirements.txt` and installs packages with zero custom configuration (no `buildCommand` required or recommended)

2. **api/index.py** — Lightweight ASGI wrapper that:
   - Imports the FastAPI app from `app/main.py`
   - Re-exports it for Vercel serverless functions
   - Handles all HTTP methods (GET, POST, PUT, PATCH, DELETE)

3. **app/main.py** — Standard FastAPI application (no changes needed)

## Deployment Steps

### 1. Prepare Repository

Ensure your repository structure includes:

```
apps/backend/
├── api/
│   └── index.py          # ← Vercel entry point
├── app/
│   ├── main.py          # FastAPI app
│   ├── core.py          # Database, LLM logic
│   ├── config.py        # Settings
│   └── schemas.py       # Pydantic models
├── vercel.json          # ← Vercel configuration
├── requirements.txt     # Python dependencies
└── pyproject.toml       # Optional: project metadata
```

### 2. Connect to Vercel

```bash
# Option A: Use Vercel CLI (if installed)
vercel --prod

# Option B: Via Vercel Dashboard
1. Go to vercel.com
2. Import repository
3. Select "apps/backend" as root directory
4. Vercel auto-detects vercel.json
```

### 3. Set Environment Variables

In Vercel Dashboard → Settings → Environment Variables, add:

```
DATABASE_URL=postgresql://user:pass@host/db?sslmode=require
LLM_PROVIDER=gemini
LLM_MODEL=gemini-3.1-flash-lite
LLM_API_KEY=AIzaSy...
FRONTEND_BASE_URL=https://your-frontend.vercel.app
```

### 4. Deploy

Push to GitHub → Vercel auto-deploys → Monitor logs in Vercel Dashboard

## Verification

### Test Health Endpoint

```bash
curl https://your-backend.vercel.app/api/v1/health
```

Expected response:
```json
{
  "status": "healthy",
  "llm": {
    "provider": "gemini",
    "model": "gemini-3.1-flash-lite",
    "healthy": true,
    "error_code": null
  }
}
```

### Check Logs

In Vercel Dashboard:
1. Go to your project
2. Click "Functions" tab
3. Click `api/index.py`
4. View recent logs and errors

## How Vercel Serverless Python Works

### Cold Start

When a request comes in:

1. Vercel starts a Python 3.13 runtime container
2. Runs build command: `pip install -r requirements.txt`
3. Loads `api/index.py` and executes
4. FastAPI processes the request
5. Container stays warm for ~15 minutes for subsequent requests

### Warm Requests

If a request arrives within the warm period:
- Instant response (no cold start delay)
- FastAPI processes directly

### Cold Start Optimization

Cold starts typically take **2-5 seconds**. To minimize:

✅ Keep dependencies minimal in `requirements.txt`  
✅ Use fast LLM APIs (Gemini Flash is fastest)  
✅ Cache database connections (already done in SQLAlchemy)  
✅ Pre-warm by making test requests

## Database Connection Management

SQLAlchemy is already configured for serverless:

```python
# In core.py
if is_postgres:
    engine = create_engine(
        db_url,
        pool_pre_ping=True,      # Verify connections before use
        pool_recycle=3600,        # Recycle connections every hour
    )
```

This handles:
- Connection timeouts
- Stale connections after cold start
- Neon's aggressive connection pooling

## Common Issues

### Issue: "No module named 'app'"

**Cause**: `api/index.py` can't find the `app` module.

**Fix**: Ensure `sys.path.insert(0, ...)` is in `api/index.py` to add parent directory.

```python
# api/index.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from app.main import app
```

### Issue: Build fails with "No module named 'X'"

**Cause**: Dependency missing from `requirements.txt`.

**Fix**: Update `requirements.txt`:
```bash
pip freeze > requirements.txt  # Generate from current environment
# or manually add missing package
echo "package-name==1.2.3" >> requirements.txt
```

### Issue: 502 Bad Gateway

**Cause**: FastAPI app crashed or timeout.

**Fix**: 
1. Check Vercel logs for errors
2. Verify environment variables are set
3. Test database connection: `GET /api/v1/health`
4. Check function timeout (default 60s for serverless, may need increase for LLM calls)

### Issue: Cold start too slow

**Cause**: LLM API is slow or too many dependencies.

**Fix**:
- Use faster LLM (Gemini Flash < OpenAI GPT-4)
- Reduce `requirements.txt` size
- Move heavy imports inside endpoint functions

## Performance Notes

### Typical Response Times

| Endpoint | Cold Start | Warm Request |
|----------|-----------|--------------|
| `/health` | 2-3s | 100-200ms |
| `/improve` (tailoring) | 3-5s | 3-10s (LLM-dependent) |
| `/status` | 2-3s | 50-100ms |

### Optimization Tips

1. **Database**: Use Neon PostgreSQL (free tier)
   - Connection pooling built-in
   - Handles serverless workloads well

2. **LLM**: Use fastest available model
   - Gemini Flash: ~1-2s
   - Claude Haiku: ~1-2s
   - GPT-4o mini: ~2-3s

3. **Dependencies**: Keep requirements minimal
   - Remove unused packages
   - Use lightweight alternatives

## Vercel Limits (Free Tier)

| Resource | Limit |
|----------|-------|
| Build time | 45 minutes |
| Function timeout | 10 seconds (pro: 60s) |
| Memory per function | 512 MB |
| Bandwidth | 100 GB/month |
| Concurrent requests | 10 (pro: unlimited) |

**Note**: For LLM calls taking >10s, you may need Vercel Pro ($20/month) for 60s timeout. Alternatively, use background tasks or return 202 with polling.

## Monitoring

### Set Up Alerts

In Vercel Dashboard:
1. Settings → Observability
2. Connect Sentry, Datadog, or similar
3. Get alerts on errors and slow requests

### Key Metrics to Monitor

- Function duration (should be <5s for most endpoints)
- Cold start frequency (should decrease over time)
- Error rate (5xx responses)
- Database connection count

## Scaling Beyond Free Tier

| Tier | Cost | Benefits |
|------|------|----------|
| **Free** | $0 | 100 GB bandwidth, 10s timeout |
| **Pro** | $20/month | 60s timeout, priority support |
| **Enterprise** | Custom | Dedicated resources, SLAs |

For small projects (<1K users), free tier is sufficient.

## Advanced: Using Background Tasks

For long-running operations (>10s timeout), use FastAPI background tasks:

```python
from fastapi import BackgroundTasks

@app.post("/api/v1/heavy-operation")
async def heavy_operation(background_tasks: BackgroundTasks):
    # Start heavy operation in background
    background_tasks.add_task(long_running_task)
    # Return immediately to client
    return {"status": "processing", "task_id": "..."}
```

This prevents timeout on Vercel's 10s limit.

---

For more help, see:
- [Vercel Python Docs](https://vercel.com/docs/functions/serverless-functions/runtimes/python)
- [FastAPI Docs](https://fastapi.tiangolo.com/)
- [Neon PostgreSQL Docs](https://neon.tech/docs)
