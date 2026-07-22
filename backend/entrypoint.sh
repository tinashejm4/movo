#!/bin/sh
set -e

echo "Running checks..."
python manage.py check

echo "Running Django migrations..."
python manage.py migrate --noinput

# Optionally create superuser automatically if env vars are set
if [ "$DJANGO_SUPERUSER_USERNAME" ] && [ "$DJANGO_SUPERUSER_PASSWORD" ] && [ "$DJANGO_SUPERUSER_EMAIL" ]; then
  echo "Creating superuser..."
  python manage.py createsuperuser \
    --noinput \
    --username "$DJANGO_SUPERUSER_USERNAME" \
    --email "$DJANGO_SUPERUSER_EMAIL" || true
fi

# Start Django’s dev server, binding to Azure’s $PORT
echo "Starting Django runserver..."
exec python manage.py runserver 0.0.0.0:80
