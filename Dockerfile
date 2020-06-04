FROM python:3.8-alpine
WORKDIR /code
# ENV FLASK_APP app.py
RUN apk add --no-cache gcc musl-dev linux-headers make python3-dev openssl-dev libffi-dev git
COPY requirements.txt requirements.txt
RUN pip install -U setuptools pip
# docker overwrites the src location for editable packages so we pass in a --src path that doesnt get blatted
# https://stackoverflow.com/questions/29905909/pip-install-e-packages-dont-appear-in-docker
RUN pip install -r requirements.txt --src /usr/local/src
COPY . .
CMD ["python", "chat.py"]