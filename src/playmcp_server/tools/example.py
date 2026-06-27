"""예시 도구 모듈.

모든 도구는 타입 힌트 + docstring 을 작성한다 (FastMCP 가 스키마를 자동 생성).
새 도구를 만들 땐 이 파일을 복사해 tools/ 아래 새 모듈로 분리하고,
tools/__init__.py 의 register_tools 에서 등록한다.
"""

from mcp.server.fastmcp import FastMCP


def register_tools(mcp: FastMCP) -> None:
    """예시 도구들을 등록한다."""

    @mcp.tool()
    def greet(name: str) -> str:
        """이름을 받아 인사말을 돌려준다.

        Args:
            name: 인사할 대상의 이름.

        Returns:
            "Hello, {name}!" 형태의 인사말.
        """
        return f"Hello, {name}!"

    @mcp.tool()
    def add(a: int, b: int) -> int:
        """두 정수를 더한다.

        Args:
            a: 첫 번째 정수.
            b: 두 번째 정수.

        Returns:
            a 와 b 의 합.
        """
        return a + b
