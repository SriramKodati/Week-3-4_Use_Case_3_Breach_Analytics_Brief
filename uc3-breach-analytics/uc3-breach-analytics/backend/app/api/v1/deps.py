from fastapi import Header, HTTPException
from app.core.config import settings


def require_api_key(x_api_key: str = Header(default="")):
    if x_api_key != settings.api_key:
        raise HTTPException(401, "Invalid or missing API key")
