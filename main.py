"""梗导师 · FastAPI 主入口"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from routes import pages, api

BASE_DIR = Path(__file__).parent

app = FastAPI(title="梗导师 · 网络用语学习平台", version="2.0")

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

app.include_router(pages.router)
app.include_router(api.router)

# 初始化数据库（在 app 启动时可以轻易调用）
from db import database as db
db.init_db()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
