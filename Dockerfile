FROM python:3.12-slim

WORKDIR /app

# tells src/variables.py this is a deploy, not a local run
ENV CONTAINER_DEPLOY=True

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python3", "main.py"]
