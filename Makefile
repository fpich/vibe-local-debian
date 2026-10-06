.PHONY: run test lint format compile build check

run: ## Run the local Python/Textual CLI
	uv run vibe

test: ## Run the maintained local-fork test suite
	uv run pytest
test-legacy: ## Run legacy suites not yet reintegrated (known-failing on POSIX)
	uv run pytest tests/tools tests/core/git tests/core/paths tests/core/tools

lint: ## Lint runtime and maintained tests
	uv run ruff check vibe tests/local

format: ## Format runtime and maintained tests
	uv run ruff format vibe tests/local

compile: ## Compile Python sources
	python -m compileall -q vibe

build: ## Build pure-Python wheel
	uv build --wheel

check: compile lint test
