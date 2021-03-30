import os
import asyncio
import aioredis
import uvloop
import socket
import uuid
import contextvars
from fastapi import FastAPI, Depends, Request
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.websockets import WebSocket, WebSocketDisconnect

from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK
from aioredis.errors import ConnectionClosedError as ServerConnectionClosedError

REDIS_HOST = 'localhost'
REDIS_PORT = 6379
XREAD_TIMEOUT = 0
XREAD_COUNT = 100
NUM_PREVIOUS = 30
STREAM_MAX_LEN = 1000
ALLOWED_ROOMS = ['chat:1', 'chat:2', 'chat:3']
PORT = 9080
HOST = "0.0.0.0"

cvar_client_addr = contextvars.ContextVar('client_addr', default=None)
cvar_chat_info = contextvars.ContextVar('chat_info', default=None)
cvar_tenant = contextvars.ContextVar('tenant', default=None)
cvar_redis = contextvars.ContextVar('redis', default=None)


class CustomHeaderMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, header_value='Example'):
        print('__init__')
        super().__init__(app)
        self.header_value = header_value

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers['Custom'] = self.header_value
        return response


asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
app = FastAPI()
app.add_middleware(CustomHeaderMiddleware)
templates = Jinja2Templates(directory="templates")


def get_local_ip():
    """
    copy and paste from
    https://stackoverflow.com/questions/166506/finding-local-ip-addresses-using-pythons-stdlib
    """
    if os.environ.get('CHAT_HOST_IP', False):
        return os.environ['CHAT_HOST_IP']
    try:
        ip = [l for l in (
            [ip for ip in socket.gethostbyname_ex(socket.gethostname())[2] if
             not ip.startswith("127.")][:1], [
                [(s.connect(('8.8.8.8', 53)), s.getsockname()[0], s.close()) for s
                 in
                 [socket.socket(socket.AF_INET, socket.SOCK_DGRAM)]][0][1]]) if l][
            0][
            0]
    except OSError as e:
        print(e)
        return '127.0.0.1'

    return ip


async def get_redis_pool():
    try:
        pool = await aioredis.create_redis_pool(
            (REDIS_HOST, REDIS_PORT), encoding='utf-8')
        return pool
    except ConnectionRefusedError as e:
        print('cannot connect to redis on:', REDIS_HOST, REDIS_PORT)
        return None


async def get_chat_history():
    pass


async def ws_send_moderator(websocket: WebSocket, chat_info: dict):
    """
    wait for new items on chat stream and
    send data from server to client over a WebSocket

    :param websocket:
    :type websocket:
    :param chat_info:
    :type chat_info:
    """
    pool = await get_redis_pool()
    streams = chat_info['room'].split(',')
    latest_ids = ['$' for i in streams]
    ws_connected = True
    print(streams, latest_ids)
    while pool and ws_connected:
        try:
            events = await pool.xread(
                streams=streams,
                count=XREAD_COUNT,
                timeout=XREAD_TIMEOUT,
                latest_ids=latest_ids
            )
            for _, e_id, e in events:
                e['e_id'] = e_id
                await websocket.send_json(e)
                #latest_ids = [e_id]
        except ConnectionClosedError:
            ws_connected = False

        except ConnectionClosedOK:
            ws_connected = False


async def ws_send(websocket: WebSocket, chat_info: dict):
    """
    wait for new items on chat stream and
    send data from server to client over a WebSocket

    :param websocket:
    :type websocket:
    :param chat_info:
    :type chat_info:
    """
    pool = await get_redis_pool()
    latest_ids = ['$']
    ws_connected = True
    first_run = True
    while pool and ws_connected:
        try:
            if first_run:
                # fetch some previous chat history
                events = await pool.xrevrange(
                    stream=cvar_tenant.get() + ":stream",
                    count=NUM_PREVIOUS,
                    start='+',
                    stop='-'
                )
                first_run = False
                events.reverse()
                for e_id, e in events:
                    e['e_id'] = e_id
                    await websocket.send_json(e)
            else:
                events = await pool.xread(
                    streams=[cvar_tenant.get() + ":stream"],
                    count=XREAD_COUNT,
                    timeout=XREAD_TIMEOUT,
                    latest_ids=latest_ids
                )
                for _, e_id, e in events:
                    e['e_id'] = e_id
                    await websocket.send_json(e)
                    latest_ids = [e_id]
            #print('################contextvar ', cvar_tenant.get())
        except ConnectionClosedError:
            ws_connected = False

        except ConnectionClosedOK:
            ws_connected = False

        except ServerConnectionClosedError:
            print('redis server connection closed')
            return
    pool.close()


async def ws_recieve(websocket: WebSocket, chat_info: dict):
    """
    receive json data from client over a WebSocket, add messages onto the
    associated chat stream

    :param websocket:
    :type websocket:
    :param chat_info:
    :type chat_info:
    """

    ws_connected = False
    pool = await get_redis_pool()
    added = await add_room_user(chat_info, pool)

    if added:
        await announce(pool, chat_info, 'connected')
        ws_connected = True
    else:
        print('duplicate user error')

    while ws_connected:
        try:
            data = await websocket.receive_json()
            #print(data)
            if type(data) == list and len(data):
                data = data[0]
            fields = {
                'uname': chat_info['username'],
                'msg': data['msg'],
                'type': 'comment',
                'room': chat_info['room']
            }
            await pool.xadd(stream=cvar_tenant.get() + ":stream",
                            fields=fields,
                            message_id=b'*',
                            max_len=STREAM_MAX_LEN)
            #print('################contextvar ', cvar_tenant.get())
        except WebSocketDisconnect:
            await remove_room_user(chat_info, pool)
            await announce(pool, chat_info, 'disconnected')
            ws_connected = False

        except ServerConnectionClosedError:
            print('redis server connection closed')
            return

        except ConnectionRefusedError:
            print('redis server connection closed')
            return

    pool.close()


async def add_room_user(chat_info: dict, pool):
    #added = await pool.sadd(chat_info['room']+":users", chat_info['username'])
    added = await pool.sadd(cvar_tenant.get()+":users", cvar_chat_info.get()['username'])
    return added


async def remove_room_user(chat_info: dict, pool):
    #removed = await pool.srem(chat_info['room']+":users", chat_info['username'])
    removed = await pool.srem(cvar_tenant.get()+":users", cvar_chat_info.get()['username'])
    return removed


async def room_users(chat_info: dict, pool):
    #users = await pool.smembers(chat_info['room']+":users")
    users = await pool.smembers(cvar_tenant.get()+":users")
    print(len(users))
    return users


async def announce(pool, chat_info: dict, action: str):
    """
    add an announcement event onto the redis chat stream
    """
    users = await room_users(chat_info, pool)
    fields = {
        'msg': f"{chat_info['username']} {action}",
        'action': action,
        'type': 'announcement',
        'users': ", ".join(users),
        'room': chat_info['room']
    }
    #print(fields)

    await pool.xadd(stream=cvar_tenant.get() + ":stream",
                    fields=fields,
                    message_id=b'*',
                    max_len=STREAM_MAX_LEN)


async def chat_info_vars(username: str = None, room: str = None):
    """
    URL parameter info needed for a user to participate in a chat
    :param username:
    :type username:
    :param room:
    :type room:
    """
    if username is None and room is None:
        return {"username": str(uuid.uuid4()), "room": 'chat:1'}
    return {"username": username, "room": room}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket,
                             chat_info: dict = Depends(chat_info_vars)):
    #print('request.hostname', websocket.url.hostname)
    tenant_id = ":".join([websocket.url.hostname.replace('.', '_'),
                          chat_info['room']])
    cvar_tenant.set(tenant_id)
    cvar_chat_info.set(chat_info)


    # check the user is allowed into the chat room
    verified = await verify_user_for_room(chat_info)
    # open connection
    await websocket.accept()
    if not verified:

        print('failed verification')
        print(chat_info)
        await websocket.close()
    else:

        # spin up coro's for inbound and outbound communication over the socket
        await asyncio.gather(ws_recieve(websocket, chat_info),
                             ws_send(websocket, chat_info))


@app.websocket("/ws/moderator")
async def websocket_moderator_endpoint(websocket: WebSocket,
                             chat_info: dict = Depends(chat_info_vars)):
    # check the user is allowed into the chat room
    # verified = await verify_user_for_room(chat_info)
    # open connection

    if not chat_info['username'] == 'moderator':
        print('failed verification')
        await websocket.close()
        return

    await websocket.accept()
    # spin up coro's for inbound and outbound communication over the socket
    await asyncio.gather(ws_send_moderator(websocket, chat_info))


@app.get("/")
async def get(request: Request):
    return templates.TemplateResponse("chat.html",
                                      {"request": request,
                                       "ip": get_local_ip(),
                                       "port": PORT})


@app.get("/moderator")
async def get(request: Request):
    return templates.TemplateResponse("moderator_chat.html",
                                      {"request": request,
                                       "ip": get_local_ip(),
                                       "port": PORT})


async def verify_user_for_room(chat_info):
    verified = True
    pool = await get_redis_pool()
    if not pool:
        print('Redis connection failure')
        return False
    # check for duplicated user names
    already_exists = await pool.sismember(cvar_tenant.get()+":users", cvar_chat_info.get()['username'])
    if already_exists:
        print(chat_info['username'] +' user already_exists in ' + chat_info['room'])
        verified = False
    # check for restricted names

    # check for restricted rooms
    # check for non existent rooms
    # whitelist rooms
    if not chat_info['room'] in ALLOWED_ROOMS:
        verified = False
    pool.close()
    return verified


@app.on_event("startup")
async def handle_startup():
    try:
        pool = await aioredis.create_redis_pool(
            (REDIS_HOST, REDIS_PORT), encoding='utf-8', maxsize=20)
        cvar_redis.set(pool)
        print("Connected to Redis on ", REDIS_HOST, REDIS_PORT)
    except ConnectionRefusedError as e:
        print('cannot connect to redis on:', REDIS_HOST, REDIS_PORT)
        return


@app.on_event("shutdown")
async def handle_shutdown():
    redis = cvar_redis.get()
    redis.close()
    await redis.wait_closed()
    print("closed connection Redis on ", REDIS_HOST, REDIS_PORT)


if __name__ == "__main__":
    import uvicorn
    print(dir(app))
    print(app.url_path_for('websocket_endpoint'))
    uvicorn.run('chat:app', host=HOST, port=PORT, log_level='info', reload=True)#, uds='uvicorn.sock')
