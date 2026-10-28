# Demo web app for the Trust Account Integrity Engine. Synthetic data only.
#   docker build -t trust-engine .
#   docker run --rm -p 8000:8000 trust-engine        then open http://localhost:8000
# Run the tests inside the image:  docker run --rm trust-engine python -m pytest -q
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    TRUSTSENTRY_DEMO=true

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN useradd --create-home --uid 10001 app && chown -R app /app
USER app

EXPOSE 8000
# One worker: finished runs live in an in-process dict (see app.py and tests/test_deploy_config.py).
CMD gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120
