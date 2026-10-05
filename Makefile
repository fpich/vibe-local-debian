.PHONY: run test lint format compile build check

run: ## Run the local Python/Textual CLI
	uv run vibe

test: ## Run the maintained local-fork test suite
	uv run pytest

lint: ## Lint runtime and maintained tests
	uv run ruff check vibe tests/local

format: ## Format runtime and maintained tests
	uv run ruff format vibe tests/local

compile: ## Compile Python sources
	python -m compileall -q vibe

build: ## Build pure-Python wheel
	uv build --wheel

check: compile lint test
