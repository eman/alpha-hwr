.PHONY: help install dev test check format lint typecheck clean build docs serve-docs

help:  ## Show this help message
	@echo "Available targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install:  ## Install package in development mode
	pip install -e .

dev:  ## Install package with dev dependencies
	pip install -e ".[dev,docs]"

test:  ## Run tests
	pytest tests/ -v

test-cov:  ## Run tests with coverage
	pytest tests/ --cov=alpha_hwr --cov-report=term --cov-report=html

check:  ## Run all checks (format, lint, type check, test)
	@./scripts/check.sh

format:  ## Format code with ruff
	ruff format .

format-check:  ## Check code formatting
	ruff format --check .

lint:  ## Lint code with ruff
	ruff check .

lint-fix:  ## Fix linting issues
	ruff check --fix .

typecheck:  ## Run type checking with mypy and basedpyright
	mypy src/alpha_hwr
	@if command -v basedpyright >/dev/null 2>&1; then \
		basedpyright; \
	else \
		echo "basedpyright not installed, skipping..."; \
	fi

clean:  ## Clean build artifacts
	rm -rf build/ dist/ *.egg-info .pytest_cache .coverage htmlcov
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name '*.pyc' -delete

build:  ## Build package
	python -m build

docs:  ## Build documentation
	mkdocs build

serve-docs:  ## Serve documentation locally
	mkdocs serve

bump-patch:  ## Bump patch version
	bump2version patch

bump-minor:  ## Bump minor version
	bump2version minor

bump-major:  ## Bump major version
	bump2version major
