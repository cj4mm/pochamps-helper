# Pokemon Champions Helper API v11

FastAPI API for Custom GPT Actions. It fetches OP.GG Pokemon Champions data and provides single-Pokemon advice plus safe team selection, team building, and team analysis.

## v11 changes

- Team endpoints no longer fail completely when one Pokemon is missing from OP.GG.
- Unavailable Pokemon are returned in `unavailable_pokemon`.
- Team build recommendations only use candidates that successfully resolve from OP.GG.
- Alolan Ninetales aliases now resolve to `ninetales-alolan`.
- Added `/pokemon/available` candidate list endpoint.
- Added `/` health-style root response to avoid 404 at the base URL.

## Run locally

```powershell
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8080
```

Open:

```text
http://127.0.0.1:8080/docs
```

## Render

Build Command:

```text
python -m pip install --upgrade pip && python -m pip install -r requirements.txt
```

Start Command:

```text
python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

## Important Custom GPT instruction

Do not invent Pokemon candidates from general Pokemon knowledge. Use only Pokemon returned by the API or successfully resolved by OP.GG.
