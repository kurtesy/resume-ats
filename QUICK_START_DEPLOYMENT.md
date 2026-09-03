# Quick Start: Deploy to Vercel + Neon (Free)

Get Resume Matcher running on the cloud in 10 minutes.

## 1. Create Database (Neon) — 2 min

1. Go to [neon.tech](https://neon.tech) → Sign up (free)
2. Create a new project
3. Copy your **connection string** from the dashboard
   - Format: `postgres://user:password@ep-xyz.region.neon.tech/neondb?sslmode=require`

## 2. Deploy Backend (Vercel) — 4 min

1. Go to [vercel.com](https://vercel.com) → Sign up (free)
2. Import your GitHub repository
3. Create new project, select `apps/backend` as root directory
4. Add environment variables:
   ```
   DATABASE_URL=[Paste Neon connection string]
   LLM_PROVIDER=gemini
   LLM_MODEL=gemini-3.1-flash-lite
   LLM_API_KEY=[Your Gemini API key from console.cloud.google.com]
   FRONTEND_BASE_URL=https://[your-domain].vercel.app
   ```
5. Click "Deploy" → Done!
   - Copy your backend URL (e.g., `https://resume-matcher-backend.vercel.app`)

## 3. Deploy Frontend (Vercel) — 2 min

1. In Vercel dashboard, create another project
2. Import same GitHub repo, select `apps/frontend` as root directory
3. Add environment variable:
   ```
   NEXT_PUBLIC_API_URL=https://[your-backend-url]/api/v1
   ```
4. Click "Deploy" → Done!

## 4. Test

1. Visit your frontend URL (e.g., `https://resume-matcher-frontend.vercel.app`)
2. Upload a resume PDF
3. Paste a job description
4. Click "Tailor Resume"
5. ✅ Done!

## Cost

| Service | Free Tier | Price |
|---------|-----------|-------|
| Neon PostgreSQL | 1 GB storage, 3 GB bandwidth/month | $0 |
| Vercel (Backend) | 100 GB bandwidth/month | $0 |
| Vercel (Frontend) | 100 GB bandwidth/month | $0 |
| **Total** | Everything | **$0/month** |

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Backend won't deploy | Check `DATABASE_URL` format in Vercel settings |
| Frontend can't reach backend | Verify `NEXT_PUBLIC_API_URL` is set correctly |
| Database errors | Check Neon dashboard for active connections |
| 502 errors | Check backend logs in Vercel; verify env vars |

## What's Happening Under the Hood

```
[Your Domain]
    ↓
[Vercel Frontend (Next.js)]
    ↓ NEXT_PUBLIC_API_URL
[Vercel Backend (FastAPI)]
    ↓ DATABASE_URL
[Neon PostgreSQL]
```

## Scaling Up

Once you hit free tier limits:

- **Neon**: Upgrade to $15/month for more storage
- **Vercel**: Upgrade to $20/month for more functions
- **Add custom domain**: $12/year on any registrar

---

For detailed setup, see [docs/DEPLOYMENT_CHECKLIST.md](docs/DEPLOYMENT_CHECKLIST.md).

For troubleshooting, see [docs/NEON_POSTGRES_MIGRATION.md](docs/NEON_POSTGRES_MIGRATION.md).
