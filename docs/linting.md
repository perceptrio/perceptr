# Code Style Guide

This project uses automated tools to enforce a consistent code style. Here's how to work with them:

## Tools Used

- **Black**: Code formatter that enforces a consistent style
- **isort**: Sorts imports alphabetically and automatically separates them into sections
- **Flake8**: Linter that checks for logical errors and style issues
- **mypy**: Static type checker
- **Ruff**: Fast Python linter that combines many linting rules
- **pre-commit**: Runs these checks before each commit

## Setup for Development

1. Install the development dependencies with Poetry:
   ```
   poetry install --with dev
   ```

2. Install pre-commit hooks:
   ```
   poetry run pre-commit install
   ```

## Running Checks Manually

- Format code with Black:
  ```
  poetry run black app
  ```

- Sort imports with isort:
  ```
  poetry run isort app
  ```

- Run all pre-commit checks:
  ```
  poetry run pre-commit run --all-files
  ```

## VS Code Integration

If you use VS Code, the provided settings will:
- Format code on save
- Organize imports on save
- Show linting errors in real-time

## Common Issues and Solutions

- If you need to temporarily disable a specific check, you can add a comment like:
  ```python
  # noqa: F401  # Disable unused import check
  # type: ignore  # Disable mypy check
  ```

- For more complex cases, refer to each tool's documentation.
