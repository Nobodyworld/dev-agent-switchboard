PYTHON?=python3
API_BASE?=http://localhost:8000
PLAN_FILE?=.agent/PLANS.md
PLAN_REMOTE_PATH?=docs/PLANS.md

.PHONY: setup run test openapi publish-plan docker-up

setup:
	$(PYTHON) -m venv .venv
	.venv\Scripts\Activate.ps1 ; pip install -r server/requirements-dev.txt

run:
	.venv\Scripts\Activate.ps1 ; uvicorn server.app:app --reload --host 0.0.0.0 --port 8000

test:
	.venv\Scripts\Activate.ps1 ; pytest server/tests

openapi:
	curl -s $(API_BASE)/openapi.json | jq '.'

publish-plan:
	curl -X PUT $(API_BASE)/api/files/$(PLAN_REMOTE_PATH) \
		-H "Content-Type: text/markdown" --data-binary @$(PLAN_FILE)

docker-up:
	docker compose -f ops/docker-compose.yml up --build
