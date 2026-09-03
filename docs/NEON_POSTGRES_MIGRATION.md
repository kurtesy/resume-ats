# Neon PostgreSQL Migration Guide

This guide shows how to migrate Resume Matcher from SQLite to **Neon PostgreSQL** (free tier) for reliable cloud hosting on Vercel.

## Why Neon PostgreSQL?

- **Free tier**: Includes 1 GB storage, suitable for small to medium deployments
- **Serverless-friendly**: Works perfectly with Vercel's serverless functions
- **Auto-scaling**: Handles traffic spikes automatically
- **Persistent storage**: Unlike serverless containers, your data persists across deployments
- **Minimal code changes**: SQLAlchemy handles the connection transparently

## Local Development (SQLite - Default)

By default, the app uses **SQLite** locally with no configuration needed:

```bash
# Just run - SQLite is used automatically
npm run dev:backend
```

The SQLite database is stored in `apps/backend/data/database.sqlite`.

## Cloud Deployment (Neon PostgreSQL)

### Step 1: Create Neon Account & Database

1. Go to [neon.tech](https://neon.tech) and sign up (free)
2. Create a new project
3. Copy your **connection string** from the Neon dashboard
4. It looks like: `postgres://user:password@ep-xyz.us-east-1.neon.tech/neondb?sslmode=require`

### Step 2: Set Environment Variable

**For Vercel / Heroku / Railway:**

1. Go to your hosting platform's environment settings
2. Add a new variable:
   - **Key**: `DATABASE_URL`
   - **Value**: Paste the Neon connection string
3. Redeploy your backend

**For local testing with PostgreSQL:**

```bash
# In apps/backend/.env
DATABASE_URL=postgres://user:password@ep-xyz.us-east-1.neon.tech/neondb?sslmode=require

# Then restart
npm run dev:backend
```

### Step 3: Deploy Backend to Vercel

```bash
# Deploy with DATABASE_URL env var set
vercel deploy --prod
```

The database schema is created automatically on first run via SQLAlchemy's `create_all()`.

## How It Works

The app automatically selects the database based on the `DATABASE_URL` env var:

```python
# config.py
def get_database_url(self) -> str:
    if self.database_url:          # PostgreSQL if DATABASE_URL set
        return self.database_url
    return f"sqlite:///{...}"      # SQLite by default
```

**Zero code changes needed** — the same API works with both databases.

## Migrating Existing Data

If you have existing SQLite data you want to keep:

### Option A: Fresh Start (Recommended)
Simply point to the new Neon database. New data will accumulate there.

### Option B: Migrate Data
Use a tool like pgloader or manually export/import:

```bash
# Export from SQLite
sqlite3 apps/backend/data/database.sqlite ".mode csv" \
  ".output /tmp/export.sql" ".dump"

# Import to PostgreSQL (manual step-by-step via Neon console)
# Or use a Python script with SQLAlchemy to copy records
```

## Monitoring & Maintenance

**Neon Dashboard:**
- Monitor query performance
- View storage usage (free tier: 1 GB)
- Check connection stats

**Common Issues:**

| Problem | Solution |
|---------|----------|
| `sslmode` errors | Ensure `?sslmode=require` is in the connection string |
| Connection timeouts | Neon has aggressive connection pooling; use connection pooling (enabled by default in SQLAlchemy) |
| Data not persisting | Verify `DATABASE_URL` is set correctly in platform env vars |

## Rolling Back to SQLite

If you want to switch back to SQLite:

1. Remove the `DATABASE_URL` environment variable
2. Redeploy
3. The app reverts to SQLite automatically

## Performance Notes

- **SQLite** is fine for local dev and small scale (<1K users)
- **PostgreSQL (Neon)** scales better and works with serverless deployments
- Both use the same SQLAlchemy ORM layer, so queries are identical

## Architecture Diagram

```
┌─────────────────────────────────────┐
│  Resume Matcher Backend (FastAPI)   │
│  (Vercel Serverless Functions)      │
└────────────────┬────────────────────┘
                 │ DATABASE_URL env var
                 │
        ┌────────▼────────┐
        │  PostgreSQL      │
        │  (Neon Free)     │
        │  1 GB storage    │
        └─────────────────┘
```

## Next Steps

1. Deploy frontend to Vercel (automatic from GitHub)
2. Deploy backend with DATABASE_URL set
3. Verify health endpoint: `GET /api/v1/health`
4. Start tailoring resumes!

---

For questions, check the [Neon docs](https://neon.tech/docs) or [SQLAlchemy PostgreSQL guide](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html).
