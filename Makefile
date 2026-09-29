# Video Studio — local app (FastAPI back + React front) on top of the video engine.
PORT ?= 8470
BACK_PY = back/.venv/bin/python

.PHONY: install install-engine install-back install-front dev back front build start

install: install-engine install-back install-front   ## everything (engine venv, back venv, front deps)

install-engine:        ## video engine environment (.venv): torch cu124, demucs, whisper, librosa, moderngl...
	test -d .venv || uv venv .venv --python 3.11
	uv pip install --python .venv/bin/python -r requirements.txt

install-back:
	test -d back/.venv || uv venv back/.venv --python 3.12
	uv pip install --python $(BACK_PY) -r back/requirements.txt

install-front:
	cd front && pnpm install

dev:                   ## back (reload) + front (vite, http://127.0.0.1:5180)
	$(MAKE) -j2 back front

back:
	cd back && .venv/bin/uvicorn main:app --host 127.0.0.1 --port $(PORT) --reload --reload-dir .

front:
	cd front && BACK_URL=http://127.0.0.1:$(PORT) pnpm dev

build:                 ## compile the front and copy it to back/media/dist
	cd front && pnpm build
	$(BACK_PY) migrate_view.py

start: build           ## local production: http://127.0.0.1:$(PORT)
	cd back && .venv/bin/uvicorn main:app --host 127.0.0.1 --port $(PORT)
