# Deployment Checklist for Resume Matcher

## Pre-Deployment

- [ ] Commit all changes to git
- [ ] Run `npm run lint` (frontend)
- [ ] Run `npm run build` (frontend + backend)
- [ ] Verify local `npm run dev` works end-to-end

## Hosting Choice: Vercel (Recommended)

### Backend Setup (FastAPI on Vercel Functions)

1. **Create Neon PostgreSQL Database** (Free)
   - [ ] Sign up at [neon.tech](https://neon.tech)
   - [ ] Create a new database project
   - [ ] Copy the connection string (looks like: `postgres://...`)
   - [ ] Note the format: `postgres://user:password@host/dbname?sslmode=require`

2. **Deploy to Vercel**
   - [ ] Create Vercel account (free)
   - [ ] Connect GitHub repository
   - [ ] Create new project for backend
   - [ ] Add environment variables:
     - `DATABASE_URL`: Paste Neon connection string
     - `LLM_PROVIDER`: Set to your LLM provider (e.g., `gemini`, `openai`, etc.)
     - `LLM_MODEL`: Set to your model (e.g., `gemini-3.1-flash-lite`)
     - `LLM_API_KEY`: Your API key (keep this secret)
     - `FRONTEND_BASE_URL`: `https://your-frontend-domain.vercel.app`
   - [ ] Set root directory to `apps/backend`
   - [ ] Trigger deployment (should auto-deploy from git)
   - [ ] Verify health endpoint: `GET https://your-backend.vercel.app/api/v1/health`

### Frontend Setup (Next.js on Vercel)

1. **Deploy to Vercel**
   - [ ] Create new Vercel project for frontend
   - [ ] Add environment variables:
     - `NEXT_PUBLIC_API_URL`: `https://your-backend.vercel.app/api/v1`
   - [ ] Set root directory to `apps/frontend`
   - [ ] Trigger deployment
   - [ ] Verify frontend loads and can reach backend

## Alternative Hosting: Railway (All-in-One)

Railway provides a simpler one-click deployment for full-stack apps:

1. [ ] Sign up at [railway.app](https://railway.app)
2. [ ] Connect GitHub
3. [ ] Use Railway's PostgreSQL template
4. [ ] Set environment variables for backend
5. [ ] Deploy frontend and backend from same repo

**Note**: Railway's free tier is smaller than Neon. Suitable for demos but not production.

## Post-Deployment

- [ ] Test user signup / authentication flow
- [ ] Upload a test resume
- [ ] Test resume tailoring with a sample job description
- [ ] Verify PDF generation works
- [ ] Check Neon dashboard for database connections and storage usage
- [ ] Monitor Vercel logs for errors
- [ ] Set up alerts for errors (optional)

## Domain Setup (Optional)

- [ ] Purchase domain (or use free subdomain from Vercel)
- [ ] Point frontend domain to Vercel
- [ ] Update CORS settings in backend `.env` if using custom domain

## Cost Summary (Free Tier)

| Service | Free Tier | Cost |
|---------|-----------|------|
| Neon PostgreSQL | 1 GB storage, 3 GB bandwidth/month | $0 |
| Vercel Frontend | 100 GB bandwidth/month | $0 |
| Vercel Backend (Serverless) | 100 GB bandwidth/month | $0 |
| **Total** | Suitable for <1K users | **$0/month** |

## Monitoring

### Neon Dashboard
- Check storage usage (alert if >800 MB)
- Monitor active connections
- View query performance

### Vercel Dashboard
- Check function runtime (should be <1s)
- Monitor error rate
- Check bandwidth usage

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Backend won't deploy | Check `DATABASE_URL` format and env vars in Vercel settings |
| 502 errors | Check backend logs in Vercel; verify Neon connection string |
| Frontend can't reach backend | Verify `NEXT_PUBLIC_API_URL` env var and CORS settings |
| Database connection timeout | Check Neon dashboard for active connections; may need to upgrade plan |
| SSL certificate errors | Neon requires `?sslmode=require` in connection string |

## Rolling Back

If you need to revert:

1. Push a previous commit to GitHub
2. Vercel auto-deploys from the latest commit
3. For database, keep a backup of the Neon database (Vercel has snapshots feature)

## Scaling Up (After Free Tier Limits Reached)

- **Vercel Pro**: $20/month for higher function limits
- **Neon Paid**: Start at $15/month for more storage/bandwidth
- **Use CDN** (Cloudflare): $0-20/month for faster content delivery

---

For detailed setup instructions, see [NEON_POSTGRES_MIGRATION.md](./NEON_POSTGRES_MIGRATION.md).
