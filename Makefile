# vibe-local-debian helpers. The Python TUI is the only delivery surface;
# run commands from this directory so `uv run vibe` resolves.

.PHONY: run test test_contract fmt lint check clean

run:            ## Run the Python TUI
	uv run vibe

test:           ## Run the full test suite
	uv run pytest tests

test_contract:  ## Run the product contract tests only
	uv run pytest tests/contract -m contract

fmt:            ## Format Python sources
	uv run ruff format vibe tests

lint:           ## Ruff + pyright
	uv run ruff check vibe tests
	uv run pyright

check: fmt lint ## Format + lint

clean:          ## Remove caches
	rm -rf .pytest_cache .ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
