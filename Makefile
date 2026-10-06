.PHONY: run test test-legacy test-coverage lint format format-check typecheck compile build check

run: ## Run the local Python/Textual CLI
	uv run vibe

test: ## Run the maintained local-fork test suite
	uv run pytest

test-legacy: ## Run the reintegrated suites for shell/paths/git/tools surfaces
	uv run pytest tests/tools tests/core/git tests/core/paths tests/core/tools

test-coverage: ## Run the maintained suite under coverage.py
	uv run coverage run -m pytest
	uv run coverage report

lint: ## Lint runtime and maintained tests
	uv run ruff check vibe tests/local

format: ## Format runtime and maintained tests
	uv run ruff format vibe tests/local

compile: ## Compile Python sources
	python -m compileall -q vibe

typecheck: ## Type-check the runtime
	uv run pyright vibe

build: ## Build pure-Python wheel
	uv build --wheel

format-check: ## Verify formatting of runtime and maintained tests
	uv run ruff format --check vibe tests/local

check: compile lint typecheck format-check test
