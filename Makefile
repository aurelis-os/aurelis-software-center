.PHONY: test lint format check clean screenshots install-dev pre-commit

# Run all checks (lint + format + test)
check: lint format test

# Run tests
test:
	QT_QPA_PLATFORM=offscreen pytest -q

# Run linting
lint:
	ruff check src tests

# Auto-fix linting issues
lint-fix:
	ruff check --fix src tests

# Check formatting
format:
	ruff format --check src tests

# Auto-format code
format-fix:
	ruff format src tests

# Clean generated files
clean:
	rm -rf __pycache__ .pytest_cache .ruff_cache .coverage
	rm -rf src/aurelis_software/__pycache__
	rm -rf tests/__pycache__
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete

# Run screenshots generation
screenshots:
	QT_QPA_PLATFORM=offscreen python tools/screenshots.py

# Run screenshots with verbose output
screenshots-v:
	QT_QPA_PLATFORM=offscreen python tools/screenshots.py 2>&1 | grep -v "pytest_asyncio"

# Install dev dependencies
install-dev:
	pip install -e ".[dev]"

# Run all pre-commit checks
pre-commit: check
	@echo "All checks passed!"

# Default target
all: check