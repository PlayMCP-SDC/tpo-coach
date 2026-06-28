# 이미지(사진) 입력 처리 — 결론·옵션·검증

> 상태: **설계 확정(텍스트 기본 · image_url 보조) + 잔여 미지수 1개(라이브 첨부버튼 유무)**. 원래 아이디어("각자 사진을 보내 비공개로 착장 검사")의
> 사진 입력을 MCP/PlayMCP 위에서 어떻게 실현하는지 정리한 팀 공통 문서.

## TL;DR (3줄)

1. 사진은 제품 핵심이 맞다.
2. MCP 도구는 **원본 이미지 바이트**는 못 받지만 **`image_url`/`image_base64` 문자열 파라미터**로는 받을 수 있고,
   이 방식은 **PlayMCP 등록작 다수가 실제로 쓰는 검증된 길**이다(아래 실측).
3. **잔여 미지수 거의 해소(2026-06-28 조사)**: PlayMCP AI Chat은 **텍스트 입출력 중심**이고, 기존 이미지 앱들은
   **사용자가 이미지 URL을 직접 붙여넣게** 한다(호스트 자동 업로드 증거 없음). → **PlayMCP에선 텍스트 설명이 기본,
   `image_url`은 보조**. 풍부한 사진 UX는 **외부 멀티모달 호스트(Claude/ChatGPT 도구함 연결)** 경유에서만.

## 왜 도구가 원본 이미지를 직접 못 받나 (MCP 구조)

- **MCP 도구 입력 = JSON Schema(텍스트/구조화)뿐.** 이미지용 입력 타입이 스펙에 없다. `ImageContent`는 도구
  **결과(출력)**·sampling용이지 **입력**용이 아니다.
  ([MCP 스펙](https://modelcontextprotocol.io/specification/2025-06-18/server/tools),
  [디스커션 #1197](https://github.com/modelcontextprotocol/modelcontextprotocol/discussions/1197))
- 그래서 이미지는 **JSON 본문 안의 문자열(`image_url` 또는 `image_base64`)** 로만 도구에 들어갈 수 있다.
- **PlayMCP = streamable-http + stateless = JSON 본문만**(멀티파트 업로드 불가). 입력 길이 제한(후기 기준
  ~20k자)이라 **큰 base64는 부적합 → `image_url` 선호**.

## 다른 등록작으로 실측 (2026-06-28 조사)

PlayMCP 갤러리는 JS 렌더링이라, **공개 카탈로그 API `https://playmcp.kakao.com/api/v1/mcps`** 를 직접 조회해
**승인된 작품 197개 전체 + 각 도구 스키마(파라미터)** 를 1차 출처로 확인.

**이미지를 입력으로 받는 승인 작품** (우리 `check_outfit`과 동일 패턴):

| 작품 | 하는 일 | 입력 파라미터 |
| --- | --- | --- |
| 나무의사 진단도구 | 나무 사진 → 병해충 진단 | `image_url` |
| 삶은 갓생 | 목표 인증 사진 → 달성 채점 | `image_url` |
| 싸인전에(계약 건강검진) | 계약서 사진/PDF → 독소조항 분석 | `image_url`, `image_base64`, `pdf_url`, … |
| 어린이ZIP | 아이 활동 사진 → 알림장 작성 | `images[]`(URL/base64) |

확인된 사실:
- ✅ **옵션 B(`image_url`/`image_base64` 문자열)는 실증됨** — 등록·승인되어 동작 중.
- ✅ **비전 처리 앱이 승인된다 = 100ms 규칙은 하드 블로커가 아님** (계약 분석·병해충 진단은 수초 소요).
  운영상 의미 있는 한도는 **p99 3s** 쪽.
- ✅ TalkGuard(OCR 사례)는 `ocr_text`(이미 추출된 텍스트) 파라미터도 둠 → 옵션 A 패턴도 공존 가능.
- 🟡 단, 이건 "도구가 받을 수 있다"는 증거지 "호스트가 사용자 업로드 사진을 그 파라미터에 넣어준다"는 별개.

**그럼 사용자 사진은 어떻게 `image_url`로 들어가나? (2차 조사)** — 호스트 자동 업로드가 아니라 **사용자가 URL을 직접 제공**하는 방식이다:
- **앱들의 안내가 일관**: 나무의사 docstring *"사용자가 실제 사진 URL을 직접 제공한 경우에만 사용 … 임의 URL 생성 금지"*,
  삶은갓생 예시 *"오늘 인증할게 [사진 url]"*, 쿠키샷 *"이 사진으로 9컷: [이미지 URL]"*. (출처: 카탈로그 API의 starter message·도구 docstring)
- **공식 가이드 FAQ가 쐐기**: *"AI 채팅은 응답 content가 **TextContent 타입만 허용**, 이미지는 URL을 마크다운으로 텍스트에 포함.
  TextContent 외 타입은 **도구함으로 Claude/ChatGPT 직접 연결**할 때만"*. FAQ 34항목에 이미지/사진/파일 **첨부 항목 0개**.
  (출처: PlayMCP 가이드 Notion FAQ)
- → **PlayMCP AI Chat = 텍스트 입출력 중심**. 첨부 사진 자동 주입 증거 없음. 멀티모달 첨부는 외부 호스트(Claude/ChatGPT) 연결 경로에서만.

출처: [PlayMCP 카탈로그 API](https://playmcp.kakao.com/api/v1/mcps?page=0&size=100) ·
[TalkGuard OCR 서버](https://glama.ai/mcp/servers/Leejinhoe/kakao_mcp_secretary) · PlayMCP 가이드 FAQ(Notion)

## 사진을 다루는 옵션

| 옵션 | 방식 | PlayMCP |
| --- | --- | --- |
| **B. `image_url`/`image_base64` 파라미터 (실증·권장)** | 도구가 문자열로 받아 다운로드·처리(비전) | ✅ **등록작 다수가 실제 사용** |
| **A. 호스트가 사진 → 설명 변환** | 멀티모달 호스트가 사진→텍스트 변환해 도구에 텍스트 전달 | 🟡 PlayMCP 내장 지원 **미확인** |
| C. 큰 base64 직접 | 대용량 base64를 인자에 그대로 | ❌ ~20k 입력 한도 → 작은 이미지만, 일반적으로 `image_url` 권장 |

## 잔여 미지수 — 거의 해소

**도구가 `image_url`을 받는 것은 실증됨. 사용자 사진이 그 파라미터로 들어가는 방식 = "사용자가 공개 URL을 직접 붙여넣기"**
(공식 FAQ TextContent-only + 앱 docstring 근거, 신뢰도 높음). 옵션 A(호스트 자동 변환)는 PlayMCP AI Chat 네이티브 기능 아님.

**남은 단 하나 (5분 자가확인, 로그인 필요)**: PlayMCP AI Chat 라이브 UI에 **사진 첨부(클립/카메라) 버튼이 실제로 있는지**.
→ 나무의사를 도구함에 추가 → ① 첨부 버튼 유무 ② 사진 붙여서 되나 vs URL 붙여야 되나 시도. 버튼 없으면 URL 방식 확정.

## 검증 계획

### 1단계 (오늘, 배포 0) — 호스트 업로드 UI 확인
PlayMCP AI Chat(콘솔)/카카오톡 연동 채팅에 **이미지 첨부(클립/카메라) 버튼이 있는지** 본다.
- 있으면 → 사진 올리고 "이 사진 뭐 보여?"로 호스트가 보는지/텍스트화하는지 관찰
- 없으면 → 사용자 사진은 `image_url`을 직접 줘야 하는 구조일 가능성

### 2단계 (7/1 스켈레톤 등록과 합침) — 무엇이 도구로 오나
받은 인자를 그대로 돌려주는 **프로브 도구**로 확정:

```python
@mcp.tool(annotations=ToolAnnotations(
    title="Echo probe", readOnlyHint=True, destructiveHint=False,
    idempotentHint=True, openWorldHint=False))
def echo_probe(description: str = "", image_url: str = "", image_base64: str = "") -> str:
    """Echoes received args to verify what the PlayMCP host passes (TPO Coach debug)."""
    return f"description={description!r} image_url={image_url!r} base64_len={len(image_base64)}"
```

PlayMCP에서 **사진 올리고/URL 주고 "echo_probe로 확인해줘"** → 무엇이 채워지나 본다:
- `image_url`/`image_base64` 채워짐 → 옵션 B 완전 자동 ✓✓
- `description` 채워짐 → 옵션 A(호스트 텍스트 변환) ✓
- 아무것도 안 옴 → 사용자가 URL 수동 입력 필요

### ⚠️ 이걸로는 답이 안 나온다
- **MCP Inspector** — "내가 클라이언트"라 내가 넣는 대로 들어옴(호스트 행동 검증 ❌)
- **Claude Desktop** — 멀티모달이지만 PlayMCP 호스트 아님 → 일반화 금지

## 우리 도구 설계에 주는 의미

- **PlayMCP AI Chat(컨테스트 심사 surface)에선 `outfit_text`(텍스트 설명)가 기본 UX** — 사용자가 사진을 URL로
  만들어 붙이는 건 캐주얼 유저에게 불편하기 때문. ("검정 후드+청바지인데 졸업모임 괜찮아?" → 네이티브 동작)
- **`image_url`은 보조 경로로 함께 수용** (실증된 패턴, 나무의사/삶은갓생과 동일). `check_outfit`·`extract_color`(v1)가
  `outfit_text` | `image_url`(+선택 작은 `image_base64`)을 모두 받게.
- **진짜 사진 UX는 외부 멀티모달 호스트(Claude/ChatGPT 도구함 연결) 경유** 에서 빛난다 — 그 호스트가 사진을 텍스트로 변환.
- 입력 우선순위: `outfit_text` > `image_url` > `image_base64`(작은 것만).
- **프라이버시(F7)는 이제 실질 요건**: 옵션 B면 사진이 우리 서버(및 비전 API)에 도달 → **처리 후 즉시 폐기·미로깅·
  동의 고지** 강제. 비전 API 경유 시 `openWorldHint=true` 로 정직 신고.
- MVP 범위: `image_url` **파라미터 수용**은 넣되, 실제 비전 처리(외부 API)를 MVP에 넣을지는 7/1 검증·여력 보고 결정
  (텍스트 경로만으로도 핵심 루프는 성립).

## 일정 연결

[delivery-plan.md](delivery-plan.md)의 **7/1 배포·등록 조기 검증**에 합친다 — `echo_probe`로 1·2단계를 한 번에 돌려
**사진이 도구로 어떻게 도달하는지 7/1에 확정**하고, 그 결과로 `check_outfit` 입력 스키마와 v1 비전 처리 범위를 정한다.
