# redis-streams-fastapi-chat
Very simple toy example of a Redis Streams backed Chat app using Websockets, Python Asyncio and FastAPI/Starlette. (for learning purposes)

Requires Python version >= 3.6

# Installation

```shell
$ pip install -r requirements.txt
```

# Usage

```shell
$ python chat.py
```

# Networking
Be aware there are differnt layers of networking going on in this app when running with docker 
docker-compose cluster of containers are using the "links" directive in the docker-compose.yml file
this allows the chat.py script in the 'chat' container to use a hostname 'redis' to connect to the redis container.

the example 
https://docs.docker.com/compose/gettingstarted/#redis-service
does not use the 'links' directive , but this didnt work for me

https://docs.docker.com/compose/networking/
suggests using links 

however 
https://docs.docker.com/compose/compose-file/compose-file-v2/#links   

says
"Links are a legacy option. We recommend using networks instead."

Currently Docker's documentation is confusing in this respect 