FROM node:24-alpine AS widgets

WORKDIR /ui
COPY mcp_server/ui/package.json mcp_server/ui/package-lock.json ./
RUN npm ci
COPY mcp_server/ui/ ./
RUN npm run build

FROM python:3.12-slim

WORKDIR /app
COPY mcp_server/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY mcp_server/*.py ./mcp_server/
COPY --from=widgets /ui/dist ./mcp_server/ui/dist

EXPOSE 8001
CMD ["python", "-m", "mcp_server.main"]
