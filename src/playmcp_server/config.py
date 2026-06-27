"""환경변수/설정 로딩 골격.

비밀키/토큰은 .env 로만 관리한다 (.env 는 커밋 금지, .env.example 만 커밋).
.env 가 없으면 그냥 통과하고 OS 환경변수만 사용한다.
"""

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger("playmcp_server.config")


def _load_dotenv() -> None:
    """프로젝트 루트의 .env 를 읽어 os.environ 에 채운다.

    python-dotenv 가 설치돼 있으면 그것을 쓰고, 없으면 조용히 통과한다.
    이미 설정된 환경변수는 덮어쓰지 않는다.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        logger.debug("python-dotenv 미설치 — OS 환경변수만 사용")
        return
    load_dotenv(override=False)


@dataclass(frozen=True)
class Config:
    """서버 설정. 필요한 값을 여기에 추가한다."""

    log_level: str = "INFO"
    # 예) api_key: str | None = None


def load_config() -> Config:
    """.env + OS 환경변수에서 설정을 읽어 Config 를 만든다."""
    _load_dotenv()
    return Config(
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
        # 예) api_key=os.environ.get("PLAYMCP_API_KEY"),
    )
