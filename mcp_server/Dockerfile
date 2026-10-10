FROM python:3.12-slim

WORKDIR /app
COPY mcp_server/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY mcp_server ./mcp_server

EXPOSE 8001
CMD ["python", "-m", "mcp_server.main"]
