#!/bin/bash
# Local testing script for alpha-hwr
# Run all checks that will be executed in CI

set -e  # Exit on first error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "==============================================="
echo "Running local checks for alpha-hwr"
echo "==============================================="
echo ""

# Function to run a check
run_check() {
    local name=$1
    shift
    echo -e "${YELLOW}▶ Running $name...${NC}"
    if "$@"; then
        echo -e "${GREEN}✓ $name passed${NC}"
        echo ""
        return 0
    else
        echo -e "${RED}✗ $name failed${NC}"
        echo ""
        return 1
    fi
}

# Track failures
FAILED=0

# 1. Ruff format check
run_check "Ruff format" ruff format --check . || FAILED=1

# 2. Ruff lint
run_check "Ruff lint" ruff check . || FAILED=1

# 3. MyPy type checking
run_check "MyPy" mypy src/alpha_hwr || FAILED=1

# 4. Basedpyright type checking (if installed)
if command -v basedpyright &> /dev/null; then
    run_check "BasedPyright" basedpyright || FAILED=1
else
    echo -e "${YELLOW}⚠ BasedPyright not installed, skipping...${NC}"
    echo "  Install with: pip install basedpyright"
    echo ""
fi

# 5. Pytest
run_check "Pytest" pytest tests/ -v --tb=short || FAILED=1

echo "==============================================="
if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ All checks passed!${NC}"
    echo "==============================================="
    exit 0
else
    echo -e "${RED}✗ Some checks failed${NC}"
    echo "==============================================="
    exit 1
fi
