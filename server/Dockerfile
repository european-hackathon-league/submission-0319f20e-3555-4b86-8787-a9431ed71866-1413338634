FROM python:3.12-slim

WORKDIR /app
COPY server/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY server ./server
COPY mcp_server/*.py ./mcp_server/
COPY database ./database
COPY notes/source-inventory.json ./notes/source-inventory.json

EXPOSE 8000
CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8000"]
