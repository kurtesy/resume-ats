#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

FRONTEND_PORT=3000
BACKEND_PORT=8000

echo "🚀 Starting Resume Matcher in unified development mode..."

# 1. Start the Backend
echo "⚡ Starting Backend server on port $BACKEND_PORT..."
cd apps/backend
# Run backend in the background and redirect output to a local log file for clean terminal output
uv run uvicorn app.main:app --port $BACKEND_PORT --reload > backend.log 2>&1 &
BACKEND_PID=$!
cd ../..

# 2. Start the Frontend
echo "⚛️ Starting Frontend server on port $FRONTEND_PORT..."
cd apps/frontend
# Run frontend in the background and redirect output to a local log file
npm run dev -- --port $FRONTEND_PORT > frontend.log 2>&1 &
FRONTEND_PID=$!
cd ../..

# 3. Handle graceful termination (Ctrl+C)
cleanup() {
    echo ""
    echo "🛑 Stopping all servers..."
    kill $BACKEND_PID 2>/dev/null || true
    kill $FRONTEND_PID 2>/dev/null || true
    echo "✨ Clean shutdown complete!"
    exit 0
}

# Trap exit signals
trap cleanup SIGINT SIGTERM EXIT

# 4. Wait for servers to spin up and open UI
echo "🌐 Waiting for services to initialize..."
sleep 2.5

# Detect operating system and open browser
echo "💻 Opening Resume Matcher UI..."
if [[ "$OSTYPE" == "darwin"* ]]; then
    open "http://localhost:$FRONTEND_PORT"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    xdg-open "http://localhost:$FRONTEND_PORT" 2>/dev/null || true
elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || "$OSTYPE" == "win32" ]]; then
    start "http://localhost:$FRONTEND_PORT"
fi

echo "========================================================="
echo "🎉 Resume Matcher is running!"
echo "👉 Frontend URL: http://localhost:$FRONTEND_PORT"
echo "👉 Backend API Docs: http://localhost:$BACKEND_PORT/docs"
echo "📝 Backend logs are at: apps/backend/backend.log"
echo "📝 Frontend logs are at: apps/frontend/frontend.log"
echo "========================================================="
echo "⌨️  Press Ctrl+C to stop both servers."

# Keep the script running to wait for background servers
wait $BACKEND_PID $FRONTEND_PID
