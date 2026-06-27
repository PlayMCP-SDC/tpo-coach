"""예시 도구(greet, add) 동작 검증.

in-memory transport 로 도구를 실제 호출해 결과를 확인한다.
"""

import pytest

pytestmark = pytest.mark.asyncio


async def test_tools_are_listed(client_session) -> None:
    """greet, add 도구가 노출되는지 확인한다."""
    async with client_session() as client:
        result = await client.list_tools()
    names = {tool.name for tool in result.tools}
    assert {"greet", "add"} <= names


async def test_greet(client_session) -> None:
    """greet 가 인사말을 돌려주는지 확인한다."""
    async with client_session() as client:
        result = await client.call_tool("greet", {"name": "World"})
    assert result.content[0].text == "Hello, World!"


async def test_add(client_session) -> None:
    """add 가 두 정수의 합을 돌려주는지 확인한다."""
    async with client_session() as client:
        result = await client.call_tool("add", {"a": 2, "b": 3})
    assert result.content[0].text == "5"
