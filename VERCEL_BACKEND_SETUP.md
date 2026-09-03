# Vercel Backend Deployment - Quick Setup

Your FastAPI backend is now configured to deploy on Vercel's serverless Python runtime.

## What Changed

✅ Added `vercel.json` — Tells Vercel how to run your FastAPI app  
✅ Added `api/index.py` — Serverless entry point for FastAPI  
✅ Documentation — Complete guide in `docs/VERCEL_FASTAPI_DEPLOYMENT.md`

## Deploy in 3 Steps

### 1. Set Vercel Root Directory

In Vercel Dashboard for your backend project:
- **Root Directory**: `apps/backend`
- Vercel auto-detects `vercel.json`

### 2. Add Environment Variables

```
DATABASE_URL=postgresql://user:pass@ep-xyz.region.neon.tech/neondb?sslmode=require
LLM_PROVIDER=gemini
LLM_MODEL=gemini-3.1-flash-lite
LLM_API_KEY=AIzaSy...
FRONTEND_BASE_URL=https://your-frontend-domain.vercel.app
```

### 3. Deploy

Push to GitHub → Vercel auto-deploys ✅

## Verify Deployment

```bash
# Test health endpoint
curl https://your-backend.vercel.app/api/v1/health

# Should return:
# {"status":"healthy","llm":{"provider":"gemini",...}}
```

## What's Happening

```
User Request
    ↓
Vercel Edge (Global CDN)
    ↓
Python 3.13 Serverless Function
    ↓
api/index.py (entry point)
    ↓
app/main.py (FastAPI app)
    ↓
PostgreSQL via DATABASE_URL
```

## Key Features

✅ **Automatic cold start**: Python runtime spins up, installs deps, runs  
✅ **Warm caching**: Requests within 15min reuse warm container  
✅ **Database pooling**: SQLAlchemy handles connection management  
✅ **Async ready**: FastAPI async/await fully supported  
✅ **Streaming**: File uploads/downloads work fine  

## Troubleshooting

### Build Error: "No module named 'app'"

The `sys.path` fix in `api/index.py` handles this. Verify:

```python
# api/index.py should have:
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from app.main import app
```

### 502 Bad Gateway

Check Vercel logs:
1. Go to your Vercel project
2. Click **Functions** tab
3. Click `api/index.py`
4. View recent requests and errors

Common causes:
- Missing `DATABASE_URL` env var
- Invalid LLM API key
- Database connection timeout

### Slow Response (>10 seconds)

For operations taking >10s, use background tasks or upgrade to Vercel Pro (60s timeout).

## File Structure

Your backend now has:

```
apps/backend/
├── api/
│   └── index.py              ← Vercel serverless entry point
├── app/
│   ├── main.py              ← FastAPI app (unchanged)
│   ├── core.py              ← Database, LLM (unchanged)
│   └── ...
├── vercel.json              ← Vercel configuration (NEW)
├── requirements.txt         ← Python dependencies
└── pyproject.toml           ← Project metadata
```

## Performance

| Operation | Time |
|-----------|------|
| Cold start | 2-5 seconds |
| Warm request | 50ms-3s (varies by LLM) |
| Health check | 100-200ms |

## Costs

| Service | Free Tier | Price |
|---------|-----------|-------|
| Vercel | 100 GB bandwidth/month | $0 |
| Neon (PostgreSQL) | 1 GB storage | $0 |
| Total | | **$0** |

Upgrade to Vercel Pro ($20/month) only if you need:
- Longer function timeout (60s vs 10s)
- More concurrent requests
- Priority support

## Next Steps

1. **Deploy frontend** to Vercel with `NEXT_PUBLIC_API_URL` env var
2. **Test end-to-end**: Upload resume → Tailor → Verify PDF generation
3. **Monitor**: Check Vercel logs and Neon dashboard for issues
4. **Scale**: If needed, upgrade database or serverless plan

## Reference

- Full guide: [docs/VERCEL_FASTAPI_DEPLOYMENT.md](docs/VERCEL_FASTAPI_DEPLOYMENT.md)
- Vercel Python docs: https://vercel.com/docs/functions/serverless-functions/runtimes/python
- FastAPI docs: https://fastapi.tiangolo.com/

---

**Status**: ✅ Ready for Vercel deployment!
