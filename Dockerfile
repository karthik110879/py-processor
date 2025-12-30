# Dockerfile for PDF Processor Bridge
FROM python:3.10-slim

WORKDIR /app

# Install system dependencies if needed
RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN playwright install --with-deps chromium || true

# Copy application code
COPY . .

# Create upload directory
RUN mkdir -p /tmp

# Expose port
EXPOSE 5001

# Run the application
CMD ["python", "app.py"]

