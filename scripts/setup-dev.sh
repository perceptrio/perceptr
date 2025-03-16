#!/bin/bash
set -e

# Install dependencies with Poetry
poetry install --with dev

# Install pre-commit hooks
poetry run pre-commit install

echo "Development environment setup complete!"
echo "Run 'poetry run pre-commit run --all-files' to check all files"
