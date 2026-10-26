FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
# These are local execution engines, not cloud services or AI API dependencies.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-writer libreoffice-calc libreoffice-impress \
    tesseract-ocr tesseract-ocr-eng fonts-liberation fonts-dejavu-core && \
    rm -rf /var/lib/apt/lists/*
COPY requirements.txt requirements-deploy.txt ./
RUN python -m pip install --no-cache-dir --upgrade pip && \
    python -m pip install --no-cache-dir -r requirements-deploy.txt
COPY . .
RUN DJANGO_SECRET_KEY=build-only-static-collection-key DJANGO_DEBUG=False python manage.py collectstatic --noinput
EXPOSE 10000
CMD ["sh", "-c", "python manage.py migrate --noinput && gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-10000} --workers 2 --timeout 120"]
