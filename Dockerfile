# Use Python 3.9 slim as base image for smaller size
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY ddns-hosttech.py .
# Copy .env file if it exists (optional)
COPY .env* ./

# Make the script executable
RUN chmod +x ddns-hosttech.py

# Set entrypoint
ENTRYPOINT ["python", "ddns-hosttech.py"]

# Default command (can be overridden at runtime)
# Empty CMD means it will use environment variables from .env file
CMD []
