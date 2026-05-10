import asyncio
import json
import os
import time
import logging

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import aiofiles
from typing import List

from web.rest_api import router

logging.basicConfig(
    level=logging.INFO,
    format='[%(name)s %(asctime)s] %(message)s',
    datefmt='%H:%M:%S'
)
log = logging.getLogger('Web-Core5')

HOST = '0.0.0.0'
PORT = 8000
HTML_PATH =os.path.join(os.path.dirname(__file__), 'dashboard.html')
START_TIME=time.time()

app= FastAPI(title='Industrial Gateway Dashboard')
app.include_router(router)


class ConnectionManager:
    def __init__(self):
        self.active: List[WebSocket]= []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)
        log.info(f'Client connected. Total: {len(self.active)}')

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)
        log.info(f'Client disconnected. Remaining: {len(self.active)}')

    async def broadcast(self, message: str):
        dead = []
        for ws in self.active:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager=ConnectionManager()


@app.get('/')
async def serve_dashboard():
    async with aiofiles.open(HTML_PATH, 'r') as f:
        html=await f.read()
    return HTMLResponse(content=html)


@app.websocket('/ws')
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)


async def broadcast_loop(queue_ws):
    loop = asyncio.get_event_loop()
    log.info('Broadcast loop started')

    while True:
        try:
            item = await loop.run_in_executor(None, lambda: queue_ws.get(timeout=1.0))
            src= item.get('source', '')

            if src == 'mpu6050':
                continue

            if src == 'fft':
                item = {
                    'source':'fft',
                    'timestamp':item['timestamp'],
                    'dominant_freq':item['dominant_freq'],
                    'latency_ms':item['latency_ms'],
                    'fft_count':item['fft_count'],
                }

            # Add ws_clients count to every broadcast so dashboard can show it
            item['ws_clients'] = len(manager.active)

            await manager.broadcast(json.dumps(item))

        except Exception as e:
            if 'Empty' not in str(type(e).__name__):
                log.error(f'Broadcast error: {e}')
            await asyncio.sleep(0.01)


def run_server(queue_ws, stop_event):
    os.sched_setaffinity(0, {5})
    log.info('Pinned to CPU Core 5')
    log.info(f'Dashboard will be at http://<ODROID-IP>:{PORT}/')

    @app.on_event('startup')
    async def startup():
        asyncio.create_task(broadcast_loop(queue_ws))

    uvicorn.run(app, host=HOST, port=PORT, log_level='warning')