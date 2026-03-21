.PHONY: dev test lint format typecheck install clean

# ── Development ──────────────────────────────────────────────

dev:
	cd services/local-api && uvicorn app.main:app --reload --host 127.0.0.1 --port 8080

install:
	pip install -e ".[dev]"
	@for pkg in packages/*/; do \
		echo "Installing $$pkg ..."; \
		pip install -e "$$pkg" --no-deps; \
	done
	pip install -e packages/shared-types
	@echo "All packages installed."

# ── Quality ──────────────────────────────────────────────────

lint:
	ruff check .

format:
	ruff format .
	ruff check --fix .

typecheck:
	mypy packages/

test:
	pytest packages/ tests/ -q --tb=short

test-cov:
	pytest packages/ tests/ --cov=packages --cov-report=term-missing -q

# ── Cleanup ──────────────────────────────────────────────────

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name ".coverage" -delete 2>/dev/null || true
	rm -rf htmlcov/ .mypy_cache/
