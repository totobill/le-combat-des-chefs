from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, game
from app.config import settings
from app.database import async_session
from app.services.game import build_game_state, ensure_session
from app.ws.manager import ws_manager


@asynccontextmanager
async def lifespan(_app: FastAPI):
    async with async_session() as db:
        await ensure_session(db)
    yield


app = FastAPI(title="Le Combat des Chefs", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list + ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(game.router, prefix="/api")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "app": "combat-des-chefs"}


@app.websocket("/ws/{session_code}")
async def websocket_endpoint(websocket: WebSocket, session_code: str) -> None:
    await ws_manager.connect(session_code, websocket)
    try:
        async with async_session() as db:
            if session_code == settings.session_code:
                state = await build_game_state(db)
                await websocket.send_json({"type": "state_update", "state": state})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(session_code, websocket)
