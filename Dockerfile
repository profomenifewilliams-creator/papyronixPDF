# Deployment wrapper: the full Papyronix project source is uploaded as a ZIP
# in the repository root. Keep the ZIP filename exactly as shown below.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    unzip \
    libreoffice-writer libreoffice-calc libreoffice-impress \
    tesseract-ocr tesseract-ocr-eng \
    fonts-liberation fonts-dejavu-core && \
    rm -rf /var/lib/apt/lists/*

COPY PapyronixAI_Django_Local.zip /tmp/papyronix-source.zip
RUN mkdir -p /app && unzip -q /tmp/papyronix-source.zip -d /app && rm /tmp/papyronix-source.zip

WORKDIR /app
RUN python -m pip install --no-cache-dir --upgrade pip && \
    python -m pip install --no-cache-dir -r requirements-deploy.txt

RUN DJANGO_SECRET_KEY=build-only-static-collection-key DJANGO_DEBUG=False \
    python manage.py collectstatic --noinput

EXPOSE 10000
CMD ["sh", "-c", "python manage.py migrate --noinput && gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-10000} --workers 2 --timeout 120"]
