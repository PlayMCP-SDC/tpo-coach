"""도구(tool) 등록 진입점.

server.py 에서 register_tools(mcp) 를 호출한다.
새 도구 모듈을 추가하면 여기 register_tools 안에서 등록한다.

현재 스켈레톤 단계: 배포/등록 검증용 echo_probe 만 등록한다.
(예시 도구 example.py 는 템플릿으로 남겨두되 등록하지 않는다.)
"""

from mcp.server.fastmcp import FastMCP

from playmcp_server.tools import echo_probe


def register_tools(mcp: FastMCP) -> None:
    """모든 도구 모듈을 FastMCP 인스턴스에 등록한다."""
    echo_probe.register_tools(mcp)
