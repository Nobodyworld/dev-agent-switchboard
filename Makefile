PYTHON?=python3
API_BASE?=http://localhost:8000
PLAN_FILE?=.agent/PLANS.md
PLAN_REMOTE_PATH?=docs/PLANS.md

.PHONY: setup run test openapi publish-plan docker-up lint fmt typecheck security qa

setup:
	$(PYTHON) -m venv .venv
	. .venv/bin/activate && pip install -r server/requirements-dev.txt

run:
	. .venv/bin/activate && uvicorn server.app:app --reload --host 0.0.0.0 --port 8000

test:
	. .venv/bin/activate && pytest server/tests

lint:
	. .venv/bin/activate && ruff check .

fmt:
	. .venv/bin/activate && black server client/python

typecheck:
	. .venv/bin/activate && mypy --strict server/file_store.py client/python/switchboard_client.py

security:
	. .venv/bin/activate && bandit -q -r server

qa: fmt lint typecheck test security

openapi:
	curl -s $(API_BASE)/openapi.json | jq '.'

publish-plan:
	curl -X PUT $(API_BASE)/api/files/$(PLAN_REMOTE_PATH) \
		-H "Content-Type: text/markdown" --data-binary @$(PLAN_FILE)

docker-up:
	docker compose -f ops/docker-compose.yml up --build
