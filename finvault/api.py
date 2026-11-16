"""Aggregate API routes. Importing the modules registers every endpoint."""
from . import api_base, api_accounts, api_planning, api_insights, api_admin, api_scheduled  # noqa: F401
from .api_base import ApiError, Ctx, Raw, ROUTES, resolve, route  # noqa: F401

__all__ = ["ApiError", "Ctx", "Raw", "ROUTES", "resolve", "route"]
