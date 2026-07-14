"""Temporary executable entry point for the command center."""

import uvicorn
from fastapi import FastAPI

app = FastAPI()


def run() -> None:
    """Start the local command-center server."""
    uvicorn.run(app, host="127.0.0.1", port=8000)
