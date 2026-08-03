import json
import secrets
import socket

from fastapi import FastAPI, Header, HTTPException

app = FastAPI()

AUTH_TOKEN = secrets.token_urlsafe(32)


@app.get("/health")
def health(x_auth_token: str | None = Header(default=None)) -> dict:
    if x_auth_token is None or not secrets.compare_digest(x_auth_token, AUTH_TOKEN):
        raise HTTPException(status_code=401, detail="invalid token")
    return {"status": "ok"}


def build_startup_message(port: int, token: str) -> str:
    return json.dumps({"port": port, "token": token})


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def run() -> None:
    import uvicorn

    port = _find_free_port()
    print(build_startup_message(port, AUTH_TOKEN), flush=True)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    run()
