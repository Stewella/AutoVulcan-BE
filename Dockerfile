# Use a lightweight Python base image compatible with our dependencies
FROM python:3.9-slim

# Set work directory
WORKDIR /app

# Prevent Python from buffering stdout/stderr and writing .pyc files
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install Python dependencies
COPY requirements.txt ./
RUN python3 -m pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# Expose application port
EXPOSE 8000

# Default command: start FastAPI with Uvicorn
CMD ["python3", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
