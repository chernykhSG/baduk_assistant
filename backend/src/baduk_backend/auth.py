import secrets

from fastapi import Header, HTTPException

AUTH_TOKEN = secrets.token_urlsafe(32)


def verify_token(token: str | None) -> None:
    if token is None or not secrets.compare_digest(token, AUTH_TOKEN):
        raise HTTPException(status_code=401, detail="invalid token")


def require_valid_token(x_auth_token: str | None = Header(default=None)) -> None:
    verify_token(x_auth_token)
