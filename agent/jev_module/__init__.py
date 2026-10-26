"""JEV Module - AI Judge Engine for Vibe-Trading.

This module provides a fallback chain of JEV (Typesafe System One) providers
for making typed judgments (Choice/Score/Noul) with probabilities.

Architecture:
- providers.py: Configuration registry (providers.json)
- judge.py: HTTP client for calling JEV endpoints
- fallback.py: Fallback chain with 10-minute quarantine
- routes.py: FastAPI REST endpoints at /jev/*

Version: v1.0.0
"""

from .routes import router as jev_router

__all__ = ["jev_router"]
__version__ = "1.0.0"