#!/usr/bin/env bash
#
# placeholder 값을 실제 값으로 일괄 변경한다.
# 모든 파일의 문자열을 치환하고 src/<module>/ 폴더명까지 바꾼다.
#
# 사용법:
#   ./scripts/rename.sh <new-org> <new-package-name> <new_module_name> "<한 줄 설명>"
#
# 예:
#   ./scripts/rename.sh PlayMCP-SDC weather-mcp weather_mcp "날씨 정보 MCP 서버"
#
set -euo pipefail

# ---- 현재 placeholder 값 (이 골격이 생성될 때의 값) ----
OLD_ORG="PlayMCP-SDC"
OLD_PKG="playmcp-server"
OLD_MOD="playmcp_server"
OLD_DESC="PlayMCP MCP 서버 (설명을 채워주세요)"

if [ "$#" -ne 4 ]; then
  echo "사용법: $0 <new-org> <new-package-name> <new_module_name> \"<한 줄 설명>\"" >&2
  exit 1
fi

NEW_ORG="$1"
NEW_PKG="$2"
NEW_MOD="$3"
NEW_DESC="$4"

# 형식 검증
if ! [[ "$NEW_PKG" =~ ^[a-z0-9]([a-z0-9-]*[a-z0-9])?$ ]]; then
  echo "오류: package-name 은 소문자-하이픈 형식이어야 합니다: $NEW_PKG" >&2
  exit 1
fi
if ! [[ "$NEW_MOD" =~ ^[a-z][a-z0-9_]*$ ]]; then
  echo "오류: module_name 은 소문자_밑줄 형식이어야 합니다: $NEW_MOD" >&2
  exit 1
fi

# 리포 루트로 이동
cd "$(dirname "$0")/.."

# 치환 대상 파일 목록 (바이너리/캐시/가상환경 제외)
mapfile -t FILES < <(
  find . \
    -type f \
    -not -path './.git/*' \
    -not -path './.venv/*' \
    -not -path './**/__pycache__/*' \
    -not -path './.ruff_cache/*' \
    -not -path './.pytest_cache/*' \
    -not -path './uv.lock'
)

# 안전한 리터럴 치환 (perl + quotemeta; 특수문자/공백/괄호/한글 OK)
replace() {
  local search="$1" repl="$2"
  SEARCH="$search" REPLACE="$repl" perl -i -pe \
    'BEGIN{$s=quotemeta($ENV{SEARCH}); $r=$ENV{REPLACE};} s/$s/$r/g' "${FILES[@]}"
}

echo "→ 설명 치환"
replace "$OLD_DESC" "$NEW_DESC"
echo "→ 모듈명 치환: $OLD_MOD → $NEW_MOD"
replace "$OLD_MOD" "$NEW_MOD"
echo "→ 패키지명 치환: $OLD_PKG → $NEW_PKG"
replace "$OLD_PKG" "$NEW_PKG"
echo "→ 조직명 치환: $OLD_ORG → $NEW_ORG"
replace "$OLD_ORG" "$NEW_ORG"

# 모듈 폴더 이름 변경
if [ -d "src/$OLD_MOD" ] && [ "$OLD_MOD" != "$NEW_MOD" ]; then
  echo "→ 폴더 이동: src/$OLD_MOD → src/$NEW_MOD"
  if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git mv "src/$OLD_MOD" "src/$NEW_MOD"
  else
    mv "src/$OLD_MOD" "src/$NEW_MOD"
  fi
fi

echo
echo "완료. 다음을 확인하세요:"
echo "  uv sync && uv run ruff check . && uv run pytest"
echo "  git diff   # 변경 내용 검토 후 커밋"
