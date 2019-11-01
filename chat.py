import asyncio
import aioredis
import uvloop
from fastapi import FastAPI
from starlette.responses import HTMLResponse
from starlette.websockets import WebSocket

asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
app = FastAPI()
PORT = 8001
HOST = "0.0.0.0"
html = f"""
<!DOCTYPE html>
<html>
    <head>
        <title>Chat</title>
    </head>
    <body>
        <h1>WebSocket Chat</h1>
        <form action="" onsubmit="sendMessage(event)">
            <input type="text" id="messageText" autocomplete="off"/>
            <button>Send</button>
        </form>
        <ul id='messages'>
        </ul>
        <script>
            var ws = new WebSocket("ws://localhost:{PORT}/ws")
            ws.onmessage = function(event) {{
                var messages = document.getElementById('messages')
                var message = document.createElement('li')
                var content = document.createTextNode(event.data)
                message.appendChild(content)
                messages.appendChild(message)
            }};
            function sendMessage(event) {{
                var input = document.getElementById("messageText")
                ws.send(input.value)
                input.value = ''
                event.preventDefault()
            }}
        </script>
    </body>
</html>
"""


@app.get("/")
async def get():
    return HTMLResponse(html)


async def ws_send(websocket: WebSocket):
    pool = await aioredis.create_redis_pool(
        ('localhost', 6379), encoding='utf-8')
    latest_ids = ['$']
    while True:
        events = await pool.xread(
            streams=['chat:1'],
            count=100,
            timeout=10000,
            latest_ids=latest_ids
        )

        for _, e_id, e in events:
            await websocket.send_text(f"{e_id}, {e}")
            latest_ids = [e_id]


async def ws_recieve(websocket: WebSocket):
    pool = await aioredis.create_redis_pool(
        ('localhost', 6379), encoding='utf-8')
    while True:
        data = await websocket.receive_text()
        await pool.xadd(stream='chat:1',
                        fields={'msg': data},
                        message_id=b'*',
                        max_len=1000)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    await asyncio.gather(ws_recieve(websocket), ws_send(websocket))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)
