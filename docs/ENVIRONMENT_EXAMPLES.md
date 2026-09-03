# Environment Configuration Examples

This document shows example `.env` configurations for different deployment scenarios.

## Local Development (Default - SQLite)

**File: `apps/backend/.env`**

```bash
# No DATABASE_URL needed - SQLite is used automatically
# Data stored in: apps/backend/data/database.sqlite

LLM_PROVIDER=gemini
LLM_MODEL=gemini-3.1-flash-lite
LLM_API_KEY=AIzaSy...your-key...

HOST=0.0.0.0
PORT=8000
FRONTEND_BASE_URL=http://localhost:3000
```

**Start:**
```bash
npm run dev:backend
npm run dev:frontend
```

## Vercel Deployment (PostgreSQL)

### Backend Environment Variables (Vercel Dashboard)

Set these in your Vercel project settings under "Environment Variables":

```
DATABASE_URL=postgres://user:password@ep-xyz.us-east-1.neon.tech/neondb?sslmode=require
LLM_PROVIDER=gemini
LLM_MODEL=gemini-3.1-flash-lite
LLM_API_KEY=AIzaSy...your-key...
FRONTEND_BASE_URL=https://your-frontend-domain.vercel.app
```

### Frontend Environment Variables (Vercel Dashboard)

```
NEXT_PUBLIC_API_URL=https://your-backend-domain.vercel.app/api/v1
```

**Deploy:**
```bash
git push  # Auto-deploys to Vercel
```

## Railway Deployment (All-in-One)

Railway automatically sets up PostgreSQL and exposes the connection string.

### Backend Environment Variables

```
DATABASE_URL=postgres://postgres:...@container.railway.internal/railway
LLM_PROVIDER=anthropic
LLM_MODEL=claude-haiku-4-5-20251001
LLM_API_KEY=sk-ant-...your-key...
FRONTEND_BASE_URL=https://your-railway-domain.railway.app
```

### Frontend Environment Variables

```
NEXT_PUBLIC_API_URL=https://your-railway-domain.railway.app/api/v1
```

## Docker Deployment (Local PostgreSQL)

**File: `docker-compose.yml`**

```yaml
version: '3.8'
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: resumematcher
      POSTGRES_PASSWORD: secure_password
      POSTGRES_DB: resumematcher
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  backend:
    build: ./apps/backend
    environment:
      DATABASE_URL: postgres://resumematcher:secure_password@postgres:5432/resumematcher
      LLM_PROVIDER: gemini
      LLM_MODEL: gemini-3.1-flash-lite
      LLM_API_KEY: ${LLM_API_KEY}
      FRONTEND_BASE_URL: http://localhost:3000
    ports:
      - "8000:8000"
    depends_on:
      - postgres

  frontend:
    build: ./apps/frontend
    environment:
      NEXT_PUBLIC_API_URL: http://localhost:8000/api/v1
    ports:
      - "3000:3000"

volumes:
  postgres_data:
```

**Start:**
```bash
export LLM_API_KEY=AIzaSy...
docker-compose up
```

## AWS RDS + Lambda + Amplify

### Backend Lambda Function Environment

```
DATABASE_URL=postgresql://user:pass@rds-instance.amazonaws.com:5432/resumematcher
LLM_PROVIDER=openai
LLM_MODEL=gpt-5-nano-2025-08-07
LLM_API_KEY=sk-...
FRONTEND_BASE_URL=https://your-amplify-domain.amplifyapp.com
```

### Frontend Amplify Build Settings

```
NEXT_PUBLIC_API_URL=https://your-lambda-endpoint.lambda.amazonaws.com/api/v1
```

## Heroku Deployment (Postgres Add-on)

Heroku still offers paid tiers (free tier ended). Not recommended for new deployments.

If you're already on Heroku:

```bash
heroku addons:create heroku-postgresql:standard-0
heroku config:set DATABASE_URL=$(heroku config:get DATABASE_URL)
heroku config:set LLM_PROVIDER=gemini
heroku config:set LLM_API_KEY=...
git push heroku main
```

## Environment Variable Reference

| Variable | Example | Required | Notes |
|----------|---------|----------|-------|
| `DATABASE_URL` | `postgres://...` | No | Leave empty for SQLite (local only) |
| `LLM_PROVIDER` | `gemini`, `openai`, `anthropic` | Yes | LLM provider to use |
| `LLM_MODEL` | `gemini-3.1-flash-lite` | Yes | Model within the provider |
| `LLM_API_KEY` | `AIzaSy...` | Yes | API key for the provider |
| `LLM_API_BASE` | `http://localhost:11434` | No | For Ollama or custom endpoints |
| `FRONTEND_BASE_URL` | `http://localhost:3000` | No | For PDF generation links |
| `HOST` | `0.0.0.0` | No | Backend listen address |
| `PORT` | `8000` | No | Backend listen port |
| `CORS_ORIGINS` | `["http://localhost:3000"]` | No | CORS allowed origins |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000/api/v1` | No (frontend) | Backend API endpoint |

## Best Practices

1. **Never commit API keys** to git
   - Use `.env.local` (gitignored) for local development
   - Use platform secrets for production (Vercel, Railway, etc.)

2. **Different keys per environment**
   - Separate API keys for dev, staging, production
   - Rotate keys regularly

3. **PostgreSQL in production**
   - Use Neon, RDS, or equivalent for cloud deployments
   - SQLite only for local development

4. **Connection pooling**
   - Already configured for PostgreSQL in `core.py`
   - Handles serverless cold starts automatically

5. **Monitor for cost**
   - Neon free tier: 1 GB storage
   - Vercel free tier: 100 GB bandwidth/month
   - Set up alerts if approaching limits

## Switching Between Databases

**From SQLite to PostgreSQL:**
```bash
# Set DATABASE_URL to PostgreSQL connection string
export DATABASE_URL=postgres://...
npm run dev:backend
# App auto-migrates schema to PostgreSQL
```

**From PostgreSQL back to SQLite:**
```bash
# Unset DATABASE_URL
unset DATABASE_URL
npm run dev:backend
# App uses local SQLite
```

No code changes needed — SQLAlchemy handles both seamlessly.
