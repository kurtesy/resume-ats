"""Vercel serverless entry point for FastAPI application."""

import sys
from pathlib import Path

# Add virtual environment site-packages to path (created during build)
venv_path = Path(__file__).parent.parent / ".venv" / "lib"
python_version = f"python{sys.version_info.major}.{sys.version_info.minor}"
site_packages = venv_path / python_version / "site-packages"
if site_packages.exists():
    sys.path.insert(0, str(site_packages))

# Add parent directory to path so we can import app module
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.main import app

# Export the ASGI app for Vercel
__all__ = ['app']
