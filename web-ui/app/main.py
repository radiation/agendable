import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.routes import home, meetings, users

app = FastAPI(
    title="Web UI",
    version="1.0.0",
    debug=(os.getenv("ENV", "dev") == "dev"),
)

BASE_DIR = Path(__file__).parent

templates = Jinja2Templates(directory=BASE_DIR / "templates")

if app.debug:
    # clear jinja cache on each load
    templates.env.auto_reload = True
    templates.env.cache = {}

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

app.include_router(home.router)
app.include_router(users.router, prefix="/users", tags=["users"])
app.include_router(meetings.router, prefix="/meetings", tags=["meetings"])
