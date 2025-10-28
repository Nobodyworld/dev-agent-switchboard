
PYTHON?=python3
API_BASE?=http://localhost:8000
PLAN_FILE?=.agent/PLANS.md
PLAN_REMOTE_PATH?=docs/PLANS.md
VENV?=.venv
ACTIVATE=. $(VENV)/bin/activate &&

.PHONY: setup venv run test test-unit test-integration test-e2e openapi publish-plan docker-up lint fmt typecheck security qa coverage dev-bootstrap release-bump todo-check verify config

$(VENV)/.bootstrapped: server/requirements-dev.txt
	@if [ ! -d "$(VENV)" ]; then \
		$(PYTHON) -m venv $(VENV); \
	fi
	$(VENV)/bin/pip install -r server/requirements-dev.txt
	touch $@

venv: $(VENV)/.bootstrapped

setup: venv

run: venv
	$(ACTIVATE) uvicorn server.app:app --reload --host 0.0.0.0 --port 8000

test: venv
        $(ACTIVATE) pytest server/tests

test-unit: venv
	$(ACTIVATE) pytest -m unit

test-integration: venv
	$(ACTIVATE) pytest -m integration

test-e2e: venv
	$(ACTIVATE) pytest -m e2e

lint: venv
	$(ACTIVATE) ruff check .

fmt: venv
	$(ACTIVATE) black server client/python

typecheck: venv
	$(ACTIVATE) mypy --strict server/file_store.py client/python/switchboard_client.py

security: venv
	$(ACTIVATE) bandit -q -r server

todo-check:
	$(PYTHON) scripts/dev.py check-todos --root .

coverage: venv
	mkdir -p reports
	$(ACTIVATE) pytest --cov=server.extensions --cov=server.application.task_service --cov=server.application.configuration_service --cov=server.observability.diagnostics --cov=server.observability.health --cov=server.observability.activity --cov=server.observability.overview --cov-report=term-missing --cov-report=json:reports/coverage.json
	$(ACTIVATE) python scripts/dev.py coverage-gate --json reports/coverage.json \
	 --module server/extensions/loader.py=85 \
	 --module server/extensions/runtime.py=85 \
	 --module server/extensions/contracts.py=85 \
	 --module server/extensions/builtin/task_metrics.py=85 \
	 --module server/extensions/builtin/plan_metrics.py=85 \
	 --module server/extensions/builtin/plan_latency.py=80 \
	 --module server/extensions/builtin/plan_snapshot.py=80 \
	 --module server/extensions/builtin/activity_feed.py=85 \
	 --module server/extensions/observability.py=80 \
	 --module server/observability/diagnostics.py=80 \
	 --module server/observability/health.py=85 \
	 --module server/observability/activity.py=80 \
	 --module server/observability/overview.py=85 \
	 --module server/application/configuration_service.py=85

qa: fmt lint typecheck test security todo-check coverage

verify: venv
	$(ACTIVATE) python scripts/dev.py verify

dev-bootstrap:
	$(PYTHON) scripts/dev.py bootstrap --venv $(VENV)

release-bump:
	$(PYTHON) scripts/dev.py bump-version --part=patch

openapi:
	curl -s $(API_BASE)/openapi.json | jq '.'

config: venv
	$(ACTIVATE) python -m switchboard_cli config --base $(API_BASE) --agent config-cli

publish-plan:
	curl -X PUT $(API_BASE)/api/files/$(PLAN_REMOTE_PATH) \
		-H "Content-Type: text/markdown" --data-binary @$(PLAN_FILE)

docker-up:
	docker compose -f ops/docker-compose.yml up --build
