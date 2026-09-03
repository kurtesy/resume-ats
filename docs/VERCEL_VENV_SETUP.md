# Vercel Virtual Environment Setup

Your FastAPI backend now uses an explicit virtual environment on Vercel for clean dependency isolation.

## Virtual Environment Location

During Vercel's build phase, a virtual environment is created at:

```
apps/backend/.venv/
├── bin/
│   ├── python              (Python 3.13)
│   ├── pip                 (pip package manager)
│   ├── activate            (activation script)
│   └── ...other tools
├── lib/
│   └── python3.13/
│       └── site-packages/  (installed dependencies: fastapi, sqlalchemy, psycopg, etc.)
├── pyvenv.cfg             (venv configuration)
└── ...
```

## Build Process on Vercel

### Step 1: Create Virtual Environment
```bash
python -m venv .venv
```
Creates an isolated Python environment in the `.venv` directory

### Step 2: Upgrade pip
```bash
.venv/bin/pip install --upgrade pip
```
Uses the venv's pip to ensure latest version

### Step 3: Install Dependencies
```bash
.venv/bin/pip install --no-cache-dir -r requirements.txt
```
Installs all 150+ packages into `.venv/lib/python3.13/site-packages/`

## Runtime (Serverless Functions)

When a request comes in:

1. **Vercel loads the function** → `api/index.py`
2. **Entry point detects venv** → Adds `.venv/lib/python3.13/site-packages` to `sys.path`
3. **FastAPI imports work** → `import fastapi`, `import sqlalchemy`, etc. all resolve
4. **Request is processed** → FastAPI handles the route

## Environment Variables

Vercel sets these during build:

| Variable | Value | Purpose |
|----------|-------|---------|
| `PYTHONUNBUFFERED` | `1` | Unbuffered output (real-time logs) |
| `VIRTUAL_ENV` | `.venv` | Marks the active virtual environment |
| `PATH` | `.venv/bin:$PATH` | Ensures venv tools are prioritized |

## Local Development vs Vercel

### Local (your machine)
```bash
# Create venv locally
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Install dependencies
pip install -r requirements.txt

# Run server
uvicorn app.main:app --reload
```

### Vercel (cloud)
```
Build phase:
  python -m venv .venv
  .venv/bin/pip install -r requirements.txt
  
Runtime phase:
  api/index.py (re-exports FastAPI app)
  ↓
  Vercel serverless function
  ↓
  Handles requests with all dependencies available
```

## Why Virtual Environment on Vercel?

✅ **Isolation** — Packages don't interfere with Vercel's system Python  
✅ **Reproducibility** — Same venv structure locally and on Vercel  
✅ **No conflicts** — Avoids "externally-managed-environment" errors  
✅ **Clean builds** — Fresh venv each time (no stale packages)  
✅ **psycopg compatibility** — Binary wheels work without PostgreSQL dev tools  

## Viewing the venv on Vercel

To see what's installed in the venv, check the logs:

1. Go to Vercel Dashboard
2. Select your project
3. Click the deployment
4. View **Build Logs**

You'll see:
```
$ python -m venv .venv
$ .venv/bin/pip install --upgrade pip
$ .venv/bin/pip install --no-cache-dir -r requirements.txt

Collecting fastapi==0.128.4
Collecting sqlalchemy==2.0.38
Collecting psycopg==3.3.4
...
Successfully installed fastapi-0.128.4 sqlalchemy-2.0.38 psycopg-3.3.4 ... (150+ packages)
```

## Automatic Environment Management

Vercel natively manages package installation out-of-the-box. **Do not specify any custom `buildCommand` in your `vercel.json`** (e.g., trying to run `pip install` or manually create `.venv` during build). 

Specifying a custom `buildCommand` conflicts with Vercel's native Python builder `@vercel/python`, causing build failures, dirty environment states, or missing packages at runtime. Vercel automatically detects `requirements.txt` and compiles your serverless environment correctly.

## Troubleshooting

### Issue: "No module named fastapi"
- **Cause**: venv didn't build or packages didn't install
- **Check**: Vercel build logs for errors during `pip install`
- **Fix**: Verify `requirements.txt` has all dependencies and re-deploy

### Issue: Cold start is slow
- **Cause**: Creating venv on every cold start (by design)
- **Speed**: Typically 5-10 seconds (acceptable for serverless)
- **Note**: Warm requests (within 15 min) reuse the container, no venv rebuild

### Issue: Disk space exceeded
- **Cause**: 150+ packages in `.venv/` might be large
- **Solution**: Already using `--no-cache-dir` to minimize size
- **Size**: Typically ~500MB (acceptable for Vercel)

## Next Steps

1. **Deploy** to Vercel (push to GitHub)
2. **Check logs** to see venv being created
3. **Test** `GET /api/v1/health` to verify imports work
4. **Monitor** cold start times in Vercel dashboard

---

**Status**: ✅ Virtual environment is auto-created on Vercel during build phase and used at runtime.
