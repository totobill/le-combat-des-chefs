import json
from typing import Any

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect


class ConnectionManager:
    def __init__(self) -> None:
        self.active: dict[str, list[WebSocket]] = {}

    async def connect(self, session_code: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active.setdefault(session_code, []).append(websocket)

    def disconnect(self, session_code: str, websocket: WebSocket) -> None:
        conns = self.active.get(session_code, [])
        if websocket in conns:
            conns.remove(websocket)

    async def broadcast(self, session_code: str, message: dict[str, Any]) -> None:
        dead: list[WebSocket] = []
        payload = json.dumps(message, default=str)
        for ws in self.active.get(session_code, []):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(session_code, ws)


ws_manager = ConnectionManager()
