# Pokemon Champions Helper API v7

OP.GG Pokémon Champions 포켓덱스에서 포켓몬별 대표 사용률 데이터를 가져와 Custom GPT Actions에서 쓸 수 있게 만든 FastAPI MVP다.

## v7 변경점

- `raw.debug` 제거: GPT Actions에 붙여도 JSON이 길어지지 않음
- `/pokemon/{name}/advice` 추가: GPT가 바로 쓰기 좋은 대표 추정 샘플/주의점/대응법 반환
- `openapi.yaml` 운영용 정리
- `/debug/opgg/{name}`는 남겨두되 OpenAPI schema에서는 숨김

## 로컬 실행

```powershell
cd "$env:USERPROFILE\Downloads\pokemon_champions_helper_v7"
python -m venv .venv
.venv\Scripts\activate
python -m python -m pip install -r requirements.txt
python -m python -m uvicorn app.main:app --reload --port 8080
```

접속:

```text
http://127.0.0.1:8080/docs
```

## 테스트

원본 메타 데이터:

```text
http://127.0.0.1:8080/pokemon/한카리아스?refresh=true
```

GPT용 요약:

```text
http://127.0.0.1:8080/pokemon/한카리아스/advice?refresh=true
```

여러 마리 캐시 갱신:

```powershell
curl -X POST "http://127.0.0.1:8080/cache/refresh?names=한카리아스,메타그로스,루카리오"
```

## Custom GPT Actions 연결

1. Render/Railway 등에 배포한다.
2. 배포 주소를 확인한다. 예: `https://pokemon-champions-helper.onrender.com`
3. `openapi.yaml`의 서버 주소를 바꾼다.

```yaml
servers:
  - url: https://pokemon-champions-helper.onrender.com
```

4. GPT Builder → Configure → Actions → Add Action에 `openapi.yaml`을 붙여넣는다.
5. Instructions에는 `gpt_instructions.md` 내용을 붙여넣는다.

## 주의

- OP.GG 페이지 구조가 바뀌면 파서가 깨질 수 있다.
- `refresh=true`는 실시간 조회 후 캐시에 저장한다.
- `refresh=false`는 캐시 우선, 캐시가 없으면 실시간 조회를 시도한다.
- 사용률 조합으로 만든 세트는 “대표 추정 샘플”이지 실제 공개 샘플이 아니다.

## Render 배포

Render Web Service 설정값:

- Runtime: Python
- Build Command: `python -m pip install -r requirements.txt`
- Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

`render.yaml`도 포함되어 있으므로 Render Blueprint로도 배포할 수 있다.
배포 후 `https://<서비스명>.onrender.com/health`가 `{"ok": true}`를 반환하면 성공이다.
