cd apps/frontend
nohup npm run dev &
cd ../..

cd apps/backend
uv run uvicorn app.main:app --reload --port 8000
cd ../..


