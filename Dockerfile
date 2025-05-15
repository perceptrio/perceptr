FROM python:3.12.10

# Install Node.js, npm, FFmpeg and other dependencies
RUN apt-get update && apt-get install -y \
    nodejs \
    npm \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install specific rrvideo version globally
RUN npm install -g rrvideo@2.0.0-alpha.18

# Install playwright
RUN npx playwright install-deps

# Install Poetry
RUN pip install --no-cache-dir poetry

# Copy the pyproject.toml and poetry.lock files
COPY pyproject.toml poetry.lock ./

WORKDIR /app
# Install dependencies using Poetry
RUN poetry config virtualenvs.create false && poetry install --no-interaction --no-ansi

# Copy the rest of the application code into the container
COPY app/ .

# Set the default command to run the Python script
CMD ["poetry", "run", "uvicorn", "main:app", "--workers", "4", "--host", "0.0.0.0", "--port", "8000"]
