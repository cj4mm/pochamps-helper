# Pokemon Champions Helper API v10

OP.GG Pokemon Champions 데이터를 조회해서 Custom GPT Actions에서 사용할 수 있는 배틀 도우미 API입니다.

## 주요 기능

- `GET /pokemon/{name}/advice`  
  포켓몬 1마리의 대표 추정 샘플, 위협 포인트, 대응법 반환

- `GET /pokemon/{name}/profile`  
  타입/역할 태그/약점/내성/무효/주요 공격 타입 추정

- `POST /team/selection`  
  내 파티 3~6마리와 상대 파티 1~6마리를 받아 3마리 선출 TOP 3 추천

- `POST /team/build`  
  핵심 포켓몬 1~3마리 기준으로 추천 6마리 파티 생성

- `POST /team/analyze`  
  파티 약점 겹침, 역할 부족, 강점/주의점 분석

## 로컬 실행

```powershell
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8080
```

## 테스트

```text
http://127.0.0.1:8080/health
http://127.0.0.1:8080/pokemon/garchomp/advice?refresh=true
```

팀 선출 테스트:

```bash
curl -X POST "http://127.0.0.1:8080/team/selection" ^
  -H "Content-Type: application/json" ^
  -d "{\"my_team\":[\"한카리아스\",\"메타그로스\",\"리자몽\",\"따라큐\",\"마스카나\",\"누리레느\"],\"opponent_team\":[\"브리두라스\",\"라이츄\",\"리자몽\",\"메타그로스\",\"알로라 나인테일\",\"번치코\"],\"refresh\":false}"
```

## Render 배포 설정

Build Command:

```bash
python -m pip install --upgrade pip && python -m pip install -r requirements.txt
```

Start Command:

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

## Custom GPT Actions

`openapi.yaml`의 `servers.url`을 Render 주소로 바꾼 뒤, GPT Actions 스키마에 붙여넣으세요.

## 주의

팀 선출/파티 추천은 OP.GG 사용률 데이터와 내장 타입/역할 휴리스틱 기반입니다. 확정 대미지/스피드 계산은 별도 계산기가 필요합니다.
