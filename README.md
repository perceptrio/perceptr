# Perceptr

## Prerequisites
- Python 3.11 or higher
- PostgreSQL
- uv (Python package manager)

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd perceptr
```

2. Install uv (if not already installed):
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

3. Install dependencies using uv:
```bash
uv sync
```

3. Create a `.env` file:
```bash
cp .env.example .env
```

4. Update the `.env` file with your configuration:
```env
DATABASE_URL="postgresql://postgres:postgres@localhost:5432/perceptr"
SECRET_KEY="your-secure-secret-key"  # Change this in production!
```

## Database Setup

1. Create the database:
```bash
createdb perceptr
```

2. Run database migrations:
```bash
uv run alembic upgrade head
```

If you need to reset migrations:
```bash
# Drop and recreate database
dropdb perceptr
createdb perceptr

# Remove old migrations
rm -f alembic/versions/*

# Create new migration
alembic revision --autogenerate -m "init"

# Apply migration
alembic upgrade head

# Downgrade/Upgrade Alembic
alembic upgrade <target-revision> || alembic downgrade <target-revision>
```

## Running the Application

1. Start the server using uv:
```bash
uv run uvicorn main:app --reload --workers 4 --host 0.0.0.0 --port 8000
```

Or run it as a Python script:
```bash
uv run python main.py
```

The API will be available at `http://localhost:8000`

## API Endpoints

### Authentication
- `POST /api/v1/orgs/signup` - Create new account
- `POST /api/v1/orgs/login` - Login with JSON body
- `POST /api/v1/orgs/token` - OAuth2 compatible login
- `GET /api/v1/orgs/me` - Get current organization info

### Admin Organization Management
- `GET /api/v1/orgs` - List all orgs
- `GET /api/v1/orgs/{org_id}` - Get specific organization
- `PUT /api/v1/orgs/{org_id}` - Update organization
- `DELETE /api/v1/orgs/{org_id}` - Delete organization

## Example API Usage

### Create Account
```bash
curl -X POST http://localhost:8000/api/v1/orgs/signup \
  -H "Content-Type: application/json" \
  -d '{
    "name": "John Doe",
    "email": "john@example.com",
    "password": "secretpassword123"
  }'
```

### Login
```bash
curl -X POST http://localhost:8000/api/v1/orgs/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "john@example.com",
    "password": "secretpassword123"
  }'
```

### Get User Profile
```bash
curl http://localhost:8000/api/v1/orgs/me \
  -H "Authorization: Bearer your-token-here"
```

## Code Style and Linting

This project uses several tools to maintain code quality and consistency:

- **Black** for code formatting
- **isort** for import sorting
- **Flake8** and **Ruff** for linting
- **mypy** for type checking

To set up your development environment with these tools:

```bash
# Install dependencies including dev tools
uv pip install -e ".[dev]"

# Install pre-commit hooks
uv run pre-commit install
```

For more details, see [docs/linting.md](docs/linting.md).

## AWS ECS
we are using aws ecs to run the application. the ecs exec command is used to execute commands in the container. the logs command is used to view the logs of the container.

Note: make sure you have the correct permissions to use the ecs exec command. and correct permissions to access the cluster.

### aws ecs exec
aws ecs execute-command --cluster perceptr-prod-cluster --task 4fb487f2141f4a4dbe36f4274c79ce9a --container api --command "alembic upgrade head" --interactive

### aws ecs logs
aws ecs logs --cluster perceptr-prod-cluster --task 4fb487f2141f4a4dbe36f4274c79ce9a --container api --since 1d
