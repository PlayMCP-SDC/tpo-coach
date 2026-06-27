FROM python:3.12-slim

WORKDIR /app

# uv 바이너리 복사 (공식 권장 방식)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# 의존성 파일 먼저 복사 (레이어 캐시 활용). README.md 는 hatchling 빌드에 필요.
COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/

# 패키지 설치
RUN uv pip install --system -e .

# Streamable HTTP + Stateless 모드로 기동 (PlayMCP in KC 요구사항)
ENV MCP_TRANSPORT=streamable-http \
    HOST=0.0.0.0 \
    PORT=8000

EXPOSE 8000

# 엔드포인트: http://<host>:8000/mcp
CMD ["playmcp-server"]
