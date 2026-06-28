# 이미지(사진) 입력 처리 — 결론·옵션·검증 계획

> 상태: **결론 확정 + 검증 대기**. 원래 아이디어("각자 사진을 보내 비공개로 착장 검사")의 사진 입력을
> MCP/PlayMCP 위에서 어떻게 실현하는지 정리한 문서. 팀 공통 인지용.

## TL;DR (3줄)

1. 사진은 제품 핵심이 맞다.
2. **그런데 MCP 도구는 원본 이미지를 입력으로 못 받는다** — 도구 입력은 텍스트/JSON(JSON Schema)뿐이다.
3. 그래서 사진은 **"멀티모달 호스트 LLM이 보고 → 도구엔 텍스트로"** 넘기는 구조다. 이게 PlayMCP에서
   되는지는 **미확인** → **7/1 스켈레톤 등록 때 실제로 검증**한다.

## 왜 도구가 사진을 직접 못 받나 (MCP 구조적 사실)

- **MCP 도구 입력 = JSON Schema(텍스트/구조화)뿐.** 이미지용 입력 타입이 스펙에 없다.
  `ImageContent`는 도구 **결과(출력)**·sampling용이지 **입력**용이 아니다.
  ([MCP 스펙](https://modelcontextprotocol.io/specification/2025-06-18/schema),
  [메인테이너 디스커션 #1197](https://github.com/modelcontextprotocol/modelcontextprotocol/discussions/1197))
- **FastMCP(Python SDK)도 이미지 입력 전용 타입 없음** → `str`(base64 또는 URL) 파라미터 우회가 전부.
- **PlayMCP = streamable-http + stateless = JSON 본문만**(멀티파트 업로드 불가). 입력 길이 제한(후기 기준
  ~20k자)이라 **base64 이미지는 사실상 못 넣음**. 응답 100ms/p99 3s 성능 규칙과도 충돌.

→ 즉 "텍스트 입력"은 시간을 아끼려 자른 게 아니라 **MCP가 원래 도구에 사진을 안 주는 구조**다.

## 사진을 다루는 3가지 옵션

| 옵션 | 방식 | PlayMCP 적합성 |
| --- | --- | --- |
| **A. 호스트가 사진 → 설명 변환 (권장)** | 멀티모달 호스트 LLM이 사진을 읽어 "네이비 코트+베이지 슬랙스+로퍼"로 변환 → 도구엔 **텍스트** 전달 | ✅ 구조에 맞음. **단 호스트 멀티모달 여부 미확인** |
| **B. 이미지 URL 파라미터** | `image_url: str` 받아 도구가 다운로드·처리 | 🟡 가능하나 처리 시 100ms/프라이버시 비용 + 호스트가 URL을 줘야 함 |
| **C. base64 직접** | `str` + `b64decode()` | ❌ 20k 한도·성능·프라이버시로 PlayMCP 부적합(로컬 테스트만) |

## 결정적 미지수

**"PlayMCP 호스트가 ① 멀티모달이고 ② 이미지에서 뽑은 정보를 MCP 도구 호출 인자로 넘겨주는가?"**
— 공식 문서에서 확인 안 됨. 추론 불가, **실측만이 답**.

- 멀티모달 + 도구 전달 O → 옵션 A. 사용자는 사진 보내고, 우리 도구는 텍스트만 받으면 됨. **현 설계 그대로.**
- 아니면 → 옵션 B(URL) 또는 사용자가 직접 텍스트 묘사. 이건 플랫폼 한계지 우리 설계 문제 아님.

## 검증 계획 (싼 것 → 확실한 것)

### 1단계 (오늘, 배포 0) — 호스트가 이미지를 "보긴" 하나
PlayMCP AI Chat(콘솔) 또는 카카오톡 연동 채팅에 **사진 올리고 "이 사진에 뭐가 보여?"**
- 묘사함 → 멀티모달 ✓ (필요조건) / "못 본다"·무시 → 옵션 B로 / 첨부 UI 없음 → 텍스트 전용 호스트(답 확정)

### 2단계 (7/1 스켈레톤 등록과 합침) — 도구에 "뭘 넘기는지"
받은 인자를 그대로 돌려주는 **프로브 도구**로 확인:

```python
@mcp.tool(annotations=ToolAnnotations(
    title="Echo probe", readOnlyHint=True, destructiveHint=False,
    idempotentHint=True, openWorldHint=False))
def echo_probe(description: str = "", image_url: str = "") -> str:
    """Echoes received args to verify what the PlayMCP host passes (TPO Coach debug)."""
    return f"description={description!r} | image_url={image_url!r}"
```

배포·등록 후 PlayMCP에서 **사진 올리고 "이 착장을 echo_probe로 확인해줘"**:
- `description` 채워짐 → **옵션 A 성립** (도구 텍스트 입력 그대로) ✓✓
- `image_url` 채워짐 → **옵션 B 가능**
- 아무것도 안 옴/도구 미호출 → 호스트가 이미지→도구 전달 안 함

> 이 프로브 서버 = 어차피 7/1에 만들 **인프라 검증 스켈레톤** 그 자체. 일석이조.

### 3단계 (병렬) — 공식 확인
PlayMCP 개발가이드/콘솔의 image·멀티모달·첨부 언급 재확인 + 문의/개발자 채널 직접 질의.

### ⚠️ 이걸로는 답이 안 나온다
- **MCP Inspector** — "내가 클라이언트"라 내가 넣는 대로 들어옴. 호스트 행동 검증 ❌
- **Claude Desktop** — 멀티모달이지만 PlayMCP 호스트 아님 → Claude 결과를 PlayMCP로 일반화 금지

진짜 답은 **PlayMCP 위에서만** 나온다.

## 해석표 → 어느 옵션으로 가나

| 1단계(사진 묘사) | 2단계(도구 전달) | 결론 |
| --- | --- | --- |
| 됨 | `description` 채워짐 | **옵션 A** — 도구 텍스트 입력 그대로 (최선, 코드 변경 0) |
| 됨 | `image_url` 채워짐 | **옵션 B** — `image_url` 파라미터로 처리 |
| 됨 | 아무것도 안 옴 | 사용자가 직접 텍스트 묘사 입력 (수동 폴백) |
| 안됨 | — | 사진 경로 불가, 텍스트/URL only |

## 우리 도구 설계에 주는 의미

- **`check_outfit`·`extract_color` 입력 = 구조화 착장 설명**(`items[]`, `colors[]`)으로 설계한다.
  사진이든 텍스트든 호스트가 이걸로 변환해 넘기므로 **둘 다 같은 도구로 처리**된다. 사진 전용 코드 불필요.
- **옵션 B(`image_url`)는 v1 폴백**으로만 남겨둔다 (호스트가 비멀티모달일 때 대비).
- **프라이버시(F7) 유리**: 옵션 A면 사진은 호스트(카카오) 쪽에서만 처리되고 **우리 서버는 사진을 안 본다**
  → "사진 외부 미전송" 원칙에 더 부합. 사진 처리 부담이 호스트로 넘어간다.

## 일정 연결

[delivery-plan.md](delivery-plan.md)의 **7/1 배포·등록 조기 검증**에 이 검증을 합친다 — `echo_probe`로
1·2단계를 한 번에 돌려 **사진 지원 여부를 7/1에 확정**한다. 결과에 따라 `check_outfit` 입력 스키마와
v1 `extract_color`/`recommend_bottoms`의 이미지 경로 필요 여부가 갈린다.
