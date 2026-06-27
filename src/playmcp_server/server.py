"""FastMCP 서버 인스턴스와 진입점.

PlayMCP in KC 배포용: Streamable HTTP transport + Stateless 모드.
stdio transport(로컬 개발)에서는 stdout(print) 을 절대 사용하지 않는다.
모든 로그는 sys.stderr 로 보낸다 (logging.basicConfig(stream=sys.stderr)).

전송 방식은 환경변수로 고른다:
  MCP_TRANSPORT=stdio            (기본값, 로컬/uvx 용)
  MCP_TRANSPORT=streamable-http  (클라우드 배포 용 — 접속 URL 이 생긴다)
HTTP 일 때 바인딩 주소/포트:
  HOST (기본 0.0.0.0), PORT (기본 8000)
"""

import logging
import os
import sys

from mcp.server.fastmcp import FastMCP

from playmcp_server.config import load_config
from playmcp_server.tools import register_tools

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

logger = logging.getLogger("playmcp_server")

# 전송 방식 / HTTP 바인딩 설정 (환경변수)
TRANSPORT = os.environ.get("MCP_TRANSPORT", "stdio")
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8000"))

# 설정 로딩 (.env 없으면 통과)
config = load_config()

# FastMCP 인스턴스. 이름은 PACKAGE_NAME 과 맞춘다.
# host/port 는 streamable-http 전송일 때만 사용된다 (컨테이너에서 0.0.0.0 바인딩).
# stateless_http=True → 세션 없는 Stateless MCP 서버 (PlayMCP in KC 권장).
mcp = FastMCP(
    "playmcp-server",
    host=HOST,
    port=PORT,
    stateless_http=True,
    json_response=True,
)

# tools/ 아래 도구들을 등록한다.
register_tools(mcp)


def main() -> None:
    """콘솔 스크립트 진입점. MCP_TRANSPORT 환경변수로 전송 방식을 고른다.

    - 기본값 stdio (로컬 / uvx 실행)
    - 컨테이너 배포: MCP_TRANSPORT=streamable-http (PlayMCP in KC)
      → 엔드포인트 http://<host>:<port>/mcp
    """
    if TRANSPORT == "streamable-http":
        logger.info(
            "starting playmcp-server (streamable-http) on %s:%s", HOST, PORT
        )
        mcp.run(transport="streamable-http")
    else:
        logger.info("starting playmcp-server (stdio transport)")
        mcp.run()


if __name__ == "__main__":
    main()
