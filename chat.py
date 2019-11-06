import asyncio
import aioredis
import uvloop
import socket
from fastapi import FastAPI, Depends
from starlette.responses import HTMLResponse
from starlette.websockets import WebSocket, WebSocketDisconnect
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK

asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
app = FastAPI()
PORT = 8080
HOST = "0.0.0.0"


def get_local_ip():
    """
    copy and paste from
    https://stackoverflow.com/questions/166506/finding-local-ip-addresses-using-pythons-stdlib
    """
    ip = [l for l in (
        [ip for ip in socket.gethostbyname_ex(socket.gethostname())[2] if
         not ip.startswith("127.")][:1], [
            [(s.connect(('8.8.8.8', 53)), s.getsockname()[0], s.close()) for s
             in
             [socket.socket(socket.AF_INET, socket.SOCK_DGRAM)]][0][1]]) if l][
        0][
        0]
    print(ip)
    return ip


html = f"""
<!DOCTYPE html>
<html>
    <head>
        <title>Chat</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
    </head>
    <body>
        <h1>WebSocket Chat</h1>
        <form name="chat-info" id="chat-info" action="#" onsubmit="connect(event)">
            user: <input type="text" name="username" value="anon" autocomplete="off"/>
            room: <input type="text" name="room" value="chat1" autocomplete="off"/>
            <button>Send</button>
        </form>
        <ul id='messages' style="height: 60vh; overflow: scroll">
        </ul>
        <form action=""  style="height: 20vh" onsubmit="sendMessage(event)">
            <input type="text" id="messageText" autocomplete="off"/>
            <button>Send</button>
        </form>

        <script>
            var ws = null
            function connect(event) {{
                event.preventDefault()

                if (ws != null) {{
                  ws.close()
                }}

                var room_info = new URLSearchParams(new FormData(document.getElementById('chat-info'))).toString()
                ws = new WebSocket("ws://{get_local_ip()}:{PORT}/ws?" + room_info)

                ws.onmessage = function(event) {{
                    var messages = document.getElementById('messages')
                    var message = document.createElement('li')
                    var content = document.createTextNode(event.data)
                    message.appendChild(content)
                    messages.appendChild(message)
                    messages.scrollTop = messages.scrollHeight;
                }};
            }}
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


async def ws_send(websocket: WebSocket, chat_info: dict):
    pool = await aioredis.create_redis_pool(
        ('localhost', 6379), encoding='utf-8')
    latest_ids = ['$']
    connected = True
    first_run = True
    while connected:
        try:
            if first_run:
                events = await pool.xrevrange(
                    stream=chat_info['room'],
                    count=30,
                    start='+',
                    stop='-'
                )
                first_run = False
                events.reverse()
                for e_id, e in events:
                    await websocket.send_text(f"{e_id}, {e}")
            else:
                events = await pool.xread(
                    streams=[chat_info['room']],
                    count=100,
                    timeout=100000,
                    latest_ids=latest_ids
                )
                for _, e_id, e in events:
                    await websocket.send_text(f"{e_id}, {e}")
                    latest_ids = [e_id]
        except ConnectionClosedError:
            connected = False

        except ConnectionClosedOK:
            connected = False


async def ws_recieve(websocket: WebSocket, chat_info: dict):
    await announce_connected(chat_info)
    pool = await aioredis.create_redis_pool(
        ('localhost', 6379), encoding='utf-8')
    connected = True
    while connected:
        try:
            data = await websocket.receive_text()
            await pool.xadd(stream=chat_info['room'],
                            fields={
                                'username': chat_info['username'],
                                'msg': data
                            },
                            message_id=b'*',
                            max_len=1000)
        except WebSocketDisconnect:
            await announce_disconnected(chat_info)
            connected = False


async def announce_disconnected(chat_info: dict):
    pool = await aioredis.create_redis_pool(
        ('localhost', 6379), encoding='utf-8')
    await pool.xadd(stream=chat_info['room'],
                    fields={'msg': f"{chat_info['username']} disconnected"},
                    message_id=b'*',
                    max_len=1000)


async def announce_connected(chat_info: dict):
    pool = await aioredis.create_redis_pool(
        ('localhost', 6379), encoding='utf-8')
    await pool.xadd(stream=chat_info['room'],
                    fields={'msg': f"{chat_info['username']} connected"},
                    message_id=b'*',
                    max_len=1000)


async def chat_info_vars(username: str = None, room: str = None):
    return {"username": username, "room": room}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket,
                             chat_info: dict = Depends(chat_info_vars)):
    print('/ws')
    await websocket.accept()
    await asyncio.gather(ws_recieve(websocket, chat_info),
                         ws_send(websocket, chat_info))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=HOST, port=PORT)
