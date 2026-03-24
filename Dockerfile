FROM python:3.12-slim

WORKDIR /app
COPY server.py pyproject.toml ./

RUN pip install --no-cache-dir "mcp[cli]>=1.6" "httpx>=0.27" "pydantic>=2.7"

EXPOSE 8000

CMD ["python", "server.py"]
