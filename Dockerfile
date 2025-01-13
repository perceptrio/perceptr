FROM python:3.13

# Install Poetry
RUN pip install --no-cache-dir poetry


# Copy the pyproject.toml and poetry.lock files
COPY pyproject.toml poetry.lock ./

WORKDIR /app
# Install dependencies using Poetry
RUN poetry config virtualenvs.create false && poetry install --no-interaction --no-ansi

# Copy the rest of the application code into the container
COPY app/ .

# Set the default command to run the Python script (replace with your actual command)
CMD ["poetry", "run", "uvicorn", "main:app", "--reload", "--workers", "4", "--host", "0.0.0.0", "--port", "8000"]