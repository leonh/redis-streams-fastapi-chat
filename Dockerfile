FROM python:3.8-alpine
WORKDIR /code
# ENV FLASK_APP app.py
RUN apk add --no-cache gcc musl-dev linux-headers make
COPY requirements.txt requirements.txt
RUN pip install -U setuptools pip
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "chat.py"]