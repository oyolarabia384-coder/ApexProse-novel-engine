from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from engine import ensure_config_file, init_db, recover_stale_jobs
from routes_config import router as config_router
from routes_generation import router as generation_router
from routes_content import router as content_router

app = FastAPI(title="Novel Generator Web")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    ensure_config_file()
    recover_stale_jobs()


app.include_router(config_router)
app.include_router(generation_router)
app.include_router(content_router)

