import secrets

from fastapi import Header, HTTPException

AUTH_TOKEN = secrets.token_urlsafe(32)


def token_matches(token: str | None) -> bool:
    if token is None:
        return False
    return secrets.compare_digest(token.encode(), AUTH_TOKEN.encode())


def verify_token(token: str | None) -> None:
    if not token_matches(token):
        raise HTTPException(status_code=401, detail="invalid token")


def require_valid_token(x_auth_token: str | None = Header(default=None)) -> None:
    verify_token(x_auth_token)
