# Use an official Python runtime as the base image
FROM python:3.9-slim

# Install Node.js and npm
RUN apt-get update && apt-get install -y nodejs npm

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install the Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the backend code into the container
COPY backend /app/backend

# Copy the frontend code into the container
COPY frontend /app/frontend

# Install frontend dependencies
WORKDIR /app/frontend
RUN npm install

# Set back the working directory to /app
WORKDIR /app

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Expose the ports the app runs on
EXPOSE 8000 3000

# Create a startup script
RUN echo '#!/bin/bash\n\
cd /app/backend && uvicorn main:app --host 0.0.0.0 --port 8000 --reload &\n\
cd /app/frontend && npm start' > /app/start.sh

RUN chmod +x /app/start.sh

# Set the startup script as the entry point
CMD ["/app/start.sh"]