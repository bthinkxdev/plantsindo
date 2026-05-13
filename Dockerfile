# Use lightweight Python
FROM python:3.11-slim

# Set environment
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set work dir
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy project
COPY . .

# Collect static
RUN python manage.py collectstatic --noinput

# Run with Gunicorn
CMD ["gunicorn", "ecom.wsgi:application", "--bind", "0.0.0.0:8027"]