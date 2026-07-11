"""Vercel serverless entry point for FastAPI application."""

import sys
from pathlib import Path

# Add parent directory to path so we can import app module
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.main import app

# Export the ASGI app for Vercel
__all__ = ['app']
