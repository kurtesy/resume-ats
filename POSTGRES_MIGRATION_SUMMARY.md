# PostgreSQL Migration Summary

## What Changed

Resume Matcher has been migrated from **SQLite-only** to a **dual-database system** supporting both SQLite (local) and PostgreSQL (cloud).

### Code Changes

| File | Change | Impact |
|------|--------|--------|
| `apps/backend/app/config.py` | Added `database_url` setting and `get_database_url()` method | App now reads `DATABASE_URL` env var |
| `apps/backend/app/core.py` | Updated DB engine initialization with PostgreSQL support | Detects and uses PostgreSQL when URL set |
| `apps/backend/.env` | Added `DATABASE_URL` documentation and examples | Users know how to set up cloud DB |
| `pyproject.toml` | Added `psycopg2-binary==2.9.10` dependency | PostgreSQL driver for Neon/RDS |
| (New) `docs/NEON_POSTGRES_MIGRATION.md` | Complete migration guide | Users can follow step-by-step setup |
| (New) `docs/DEPLOYMENT_CHECKLIST.md` | Pre/post deployment checklist | Ensures successful deployments |
| (New) `docs/ENVIRONMENT_EXAMPLES.md` | Environment config examples | Reference for all deployment scenarios |

### Zero Code Changes for Users

The API layer (FastAPI endpoints) is **100% unchanged**. No migration needed for clients or frontend code.

## How It Works

```python
# Automatic selection based on environment
if DATABASE_URL env var is set:
    Use PostgreSQL (cloud: Neon, RDS, Railway, etc.)
else:
    Use SQLite (local development)
```

## Local Development (No Changes)

Development workflow is **unchanged**:

```bash
npm run dev:backend    # Uses SQLite by default
npm run dev:frontend
```

SQLite database is at: `apps/backend/data/database.sqlite`

## Cloud Deployment (New)

### Recommended: Vercel + Neon (Free)

1. Create free Neon PostgreSQL database: [neon.tech](https://neon.tech)
2. Copy connection string to `DATABASE_URL` env var in Vercel
3. Deploy backend → PostgreSQL is used automatically
4. No schema migration needed; tables created on first run

**Cost**: $0/month for small scale

### Alternative: Railway (Simpler)

Railway auto-provisions PostgreSQL with one click. 

**Cost**: $0-5/month depending on usage

## Testing

All existing tests pass without modification:

```bash
✓ 5 diff calculation tests
✓ /improve endpoint (was broken, now fixed)
✓ /improve/confirm endpoint (was broken, now fixed)
✓ /retry-processing endpoint (was broken, now fixed)
✓ /config/reset endpoint (message fixed)
✓ Database config (SQLite default works)
```

## What Users Need to Do

### For Local Development
**Nothing.** Everything works as before. SQLite is default.

### For Cloud Deployment to Vercel

1. Sign up for free Neon account
2. Create PostgreSQL database
3. Copy connection string
4. In Vercel environment settings, add:
   ```
   DATABASE_URL=postgres://user:pass@host/db?sslmode=require
   ```
5. Redeploy backend → Done!

**Estimated time**: 10 minutes

### For Existing Vercel Deployments

If upgrading from old version:

1. Update code: `git pull`
2. Add `DATABASE_URL` env var to Vercel (or leave empty to stay on SQLite)
3. Redeploy

No data migration needed if staying on SQLite; start fresh on PostgreSQL if desired.

## Backwards Compatibility

✅ **100% backwards compatible**

- Existing SQLite deployments continue to work unchanged
- New deployments can use SQLite (local) or PostgreSQL (cloud)
- No breaking changes to API, schemas, or database structure
- Can switch between SQLite and PostgreSQL by setting/unsetting `DATABASE_URL`

## Performance Impact

### SQLite (Local Development)
- No change; already fast for local dev
- Single-file storage in `data/` directory

### PostgreSQL (Cloud)
- **Better**: Persistent, scales automatically, works with serverless
- **Connection pooling**: Already configured for Vercel serverless
- **Cold start**: Handled transparently by SQLAlchemy

## Security Notes

- `DATABASE_URL` should be treated as a secret
- Never commit it to git
- Use platform-specific secret management (Vercel Secrets, Railway Secrets, etc.)
- Neon supports SSL by default (`?sslmode=require`)

## Rollback Plan

If PostgreSQL causes issues:

1. Remove `DATABASE_URL` from environment
2. Redeploy backend
3. App automatically reverts to SQLite
4. Existing PostgreSQL data remains untouched (if you keep the connection string)

**No code changes needed** to switch back.

## Next Steps

1. **For cloud deployment**, read [docs/NEON_POSTGRES_MIGRATION.md](docs/NEON_POSTGRES_MIGRATION.md)
2. **For deployment checklist**, see [docs/DEPLOYMENT_CHECKLIST.md](docs/DEPLOYMENT_CHECKLIST.md)
3. **For environment examples**, check [docs/ENVIRONMENT_EXAMPLES.md](docs/ENVIRONMENT_EXAMPLES.md)

## FAQ

**Q: Do I have to use PostgreSQL?**  
A: No. SQLite is default and works great for local development. PostgreSQL is recommended only for cloud deployments on Vercel/Railway.

**Q: Will my existing SQLite data transfer to PostgreSQL?**  
A: No, but you start fresh on a new cloud database. Local SQLite data stays local unless you explicitly migrate.

**Q: What if I'm already deployed and want to add PostgreSQL?**  
A: Just add the `DATABASE_URL` env var in your hosting platform and redeploy. New data goes to PostgreSQL.

**Q: Is Neon free forever?**  
A: No, but the free tier (1 GB storage) is indefinite. Paid tiers start at $15/month for more storage.

**Q: What about my old SQLite backups?**  
A: They remain in `apps/backend/data/database.sqlite` if you're running locally. Cloud deployments create new databases.

---

For questions about PostgreSQL setup, visit the [Neon docs](https://neon.tech/docs) or this repo's discussion section.
