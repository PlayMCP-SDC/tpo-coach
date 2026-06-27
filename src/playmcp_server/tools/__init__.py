"""도구(tool) 등록 진입점.

server.py 에서 register_tools(mcp) 를 호출한다.
새 도구 모듈을 추가하면 여기 register_tools 안에서 등록한다.
"""

from mcp.server.fastmcp import FastMCP

from playmcp_server.tools import example


def register_tools(mcp: FastMCP) -> None:
    """모든 도구 모듈을 FastMCP 인스턴스에 등록한다."""
    example.register_tools(mcp)
