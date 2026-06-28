"""echo_probe 도구 동작 검증.

in-memory transport 로 도구를 실제 호출해 결과를 확인한다.
"""

import pytest

pytestmark = pytest.mark.asyncio


async def test_echo_probe_is_listed(client_session) -> None:
    """echo_probe 도구가 노출되는지 확인한다."""
    async with client_session() as client:
        result = await client.list_tools()
    names = {tool.name for tool in result.tools}
    assert "echo_probe" in names


async def test_echo_probe_reports_received_fields(client_session) -> None:
    """echo_probe 가 받은 인자를 그대로 돌려주는지 확인한다."""
    async with client_session() as client:
        result = await client.call_tool(
            "echo_probe",
            {"outfit_text": "navy coat", "image_url": "https://x/y.jpg"},
        )
    text = result.content[0].text
    assert "navy coat" in text
    assert "https://x/y.jpg" in text
    assert "image_base64_len=0" in text


async def test_echo_probe_has_all_annotations(client_session) -> None:
    """PlayMCP 규칙: annotations 5종이 정직하게 지정됐는지 확인한다."""
    async with client_session() as client:
        result = await client.list_tools()
    tool = next(t for t in result.tools if t.name == "echo_probe")
    ann = tool.annotations
    assert ann is not None
    assert ann.title == "Echo probe"
    assert ann.readOnlyHint is True
    assert ann.destructiveHint is False
    assert ann.idempotentHint is True
    assert ann.openWorldHint is False
