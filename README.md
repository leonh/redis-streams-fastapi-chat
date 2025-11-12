# redis-streams-fastapi-chat
A simple demo of Redis Streams backed Chat app using Websockets, Python Asyncio and FastAPI/Starlette.

Requires Python version >= 3.11 and Redis 7+

# Overview
This project has been created to help understand some related concepts. Python standard library asyncio, websockets (which are often cited as a classic use case for async python code), also Redis Streams. It is very much inteded to be an intentionally simple starting point rather than a usable product as is.

# Installation

## Local Development

```shell
$ pip install -r requirements.txt
```

Make sure you have Redis running locally:
```shell
$ redis-server
```

# Usage

## Local Development

```shell
$ python chat.py
```

Then open http://localhost:9080 in your browser.

## Docker Compose

The easiest way to run the application with all dependencies:

```shell
$ docker-compose up
```

This will start both the chat application and Redis in containers. The app will be available at http://localhost:9080

## Environment Variables

The following environment variables can be configured:

- `REDIS_HOST` - Redis server hostname (default: `localhost`, set to `redis` in Docker)
- `REDIS_PORT` - Redis server port (default: `6379`) 

