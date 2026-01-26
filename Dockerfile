FROM python:3.12.10

# Install Node.js, npm, FFmpeg and other dependencies
RUN apt-get update && apt-get install -y \
    nodejs \
    npm \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install specific rrvideo version globally
RUN npm install -g rrvideo@2.0.0-alpha.18

# Install playwright
RUN npx playwright install-deps

# Install uv
RUN pip install --no-cache-dir uv

WORKDIR /
# Copy the pyproject.toml file first for dependency installation
COPY pyproject.toml ./

# Install dependencies using uv
RUN uv pip install --system .
# RUN uv sync

# Copy the rest of the application code into the container
COPY . .

# Set the default command to run the Python script
# CMD ["uv", "run", "main.py"]
CMD ["uvicorn", "main:app", "--workers", "4", "--host", "0.0.0.0", "--port", "8000"]
