FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN DJANGO_SECRET_KEY=build-only \
    DJANGO_DEBUG=False \
    POSTGRES_DB=build POSTGRES_USER=build POSTGRES_PASSWORD=build \
    POSTGRES_HOST=localhost POSTGRES_PORT=5432 \
    STRIPE_SECRET_KEY=build STRIPE_WEBHOOK_SECRET=build \
    STRIPE_SUCCESS_URL=http://localhost/success \
    STRIPE_CANCEL_URL=http://localhost/cancel \
    python manage.py collectstatic --noinput

RUN useradd --create-home appuser
USER appuser

EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]