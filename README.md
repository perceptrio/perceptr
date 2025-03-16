# Perceptr

## Prerequisites
- Python 3.11 or higher
- PostgreSQL
- Poetry (Python package manager)

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd perceptr
```

2. Install dependencies using Poetry:
```bash
pip install poetry
poetry install
```

3. Create a `.env` file in the app directory:
```bash
cd app
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
cd app
alembic upgrade head
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

1. Start the server (from the app directory):
```bash
cd app
uvicorn main:app --reload --workers 4 --host 0.0.0.0 --port 8000
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
poetry install --with dev

# Install pre-commit hooks
poetry run pre-commit install
```

For more details, see [docs/linting.md](docs/linting.md).
