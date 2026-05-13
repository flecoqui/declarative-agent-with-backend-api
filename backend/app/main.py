from __future__ import annotations

import logging

from dotenv import load_dotenv

load_dotenv()  # noqa: E402  must run before importing modules that read env

from fastapi import FastAPI  # noqa: E402

from .routers import tasks  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)

app = FastAPI(
    title="Declarative Agent Tasks API",
    version="1.0.0",
    description="Sample tasks API protected by Microsoft Entra ID.",
)

app.include_router(tasks.router)


@app.get("/healthz", tags=["meta"], include_in_schema=False)
def healthz() -> dict[str, str]:
    return {"status": "ok"}
