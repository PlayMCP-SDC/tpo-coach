"""공용 픽스처.

FastMCP 인스턴스를 in-memory 로 띄워 ClientSession 으로 도구를 호출한다.
실제 stdio 프로세스를 띄우지 않고 메모리 스트림으로 연결하므로 빠르고 안정적이다.

주의: async 컨텍스트매니저의 진입/종료는 같은 task 안에서 일어나야 한다
(anyio cancel scope 제약). 그래서 픽스처가 세션을 yield 하지 않고,
세션을 만드는 컨텍스트매니저 팩토리를 돌려준다. 각 테스트는
`async with client_session() as client:` 형태로 사용한다.
"""

from contextlib import asynccontextmanager

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from playmcp_server.server import mcp


@pytest.fixture
def client_session():
    """초기화까지 끝난 in-memory MCP 클라이언트 세션 컨텍스트매니저를 돌려준다."""

    @asynccontextmanager
    async def _session():
        async with create_connected_server_and_client_session(
            mcp._mcp_server
        ) as session:
            await session.initialize()
            yield session

    return _session
