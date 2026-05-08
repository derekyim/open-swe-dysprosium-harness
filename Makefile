.PHONY: all format format-check lint test tests integration_tests help run dev dev-stable playwright-install

# Default target executed when no arguments are given to make.
all: help

######################
# DEVELOPMENT
######################

# Override via env or `make dev LANGGRAPH_PORT=3000`
LANGGRAPH_HOST ?= localhost
LANGGRAPH_PORT ?= 2024

# `--allow-blocking` disables langgraph dev's blockbuster instrumentation,
# which otherwise catches sync I/O inside vendor SDKs we don't control
# (Modal's `Resolver.__init__` does sync `tempfile.TemporaryFile()`,
# Playwright's sync API, etc.). Dev-only: in production (Cloud Run +
# uvicorn) blockbuster is not active so this flag is unnecessary.
dev:
	langgraph dev --host $(LANGGRAPH_HOST) --port $(LANGGRAPH_PORT) --allow-blocking --no-browser

# Same as dev but disables file-watch auto-reload — use when an agent run
# is in flight and you don't want a code/`.env`/docs edit to kill it mid-call.
dev-stable:
	langgraph dev --host $(LANGGRAPH_HOST) --port $(LANGGRAPH_PORT) --no-reload --allow-blocking --no-browser

# Override via env or `make run RUN_PORT=9000`
RUN_PORT ?= 8000

run:
	uvicorn agent.webapp:app --reload --port $(RUN_PORT)

install:
	uv pip install -e .

# Install Chromium for the screenshot tool. Idempotent — safe to re-run.
playwright-install:
	uv run playwright install chromium

######################
# TESTING
######################

TEST_FILE ?= tests/

test tests:
	@if [ -d "$(TEST_FILE)" ] || [ -f "$(TEST_FILE)" ]; then \
		uv run pytest -vvv $(TEST_FILE); \
	else \
		echo "Skipping tests: path not found: $(TEST_FILE)"; \
	fi

integration_tests:
	@if [ -d "tests/integration_tests/" ] || [ -f "tests/integration_tests/" ]; then \
		uv run pytest -vvv tests/integration_tests/; \
	else \
		echo "Skipping integration tests: path not found: tests/integration_tests/"; \
	fi

######################
# LINTING AND FORMATTING
######################

PYTHON_FILES=.

lint:
	uv run ruff check $(PYTHON_FILES)
	uv run ruff format $(PYTHON_FILES) --diff

format:
	uv run ruff format $(PYTHON_FILES)
	uv run ruff check --fix $(PYTHON_FILES)

format-check:
	uv run ruff format $(PYTHON_FILES) --check

######################
# HELP
######################

help:
	@echo '----'
	@echo 'dev                          - run LangGraph dev server (file-watch reload on)'
	@echo 'dev-stable                   - run dev server with --no-reload (for long-running tasks)'
	@echo 'run                          - run webhook server'
	@echo 'install                      - install dependencies'
	@echo 'playwright-install           - install Chromium for the screenshot tool'
	@echo 'format                       - run code formatters'
	@echo 'lint                         - run linters'
	@echo 'test                         - run unit tests'
	@echo 'integration_tests            - run integration tests'
