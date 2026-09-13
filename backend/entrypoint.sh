#!/bin/sh
set -e

echo "Running checks..."
python manage.py check

echo "Running Django migrations..."
python manage.py migrate --noinput

echo "Running Django migrations..."
python manage.py collectstatic --noinput

# Optionally create superuser automatically if env vars are set
if [ "$DJANGO_SUPERUSER_USERNAME" ] && [ "$DJANGO_SUPERUSER_PASSWORD" ] && [ "$DJANGO_SUPERUSER_EMAIL" ]; then
  echo "Creating superuser..."
  python manage.py createsuperuser \
    --noinput \
    --username "$DJANGO_SUPERUSER_USERNAME" \
    --email "$DJANGO_SUPERUSER_EMAIL" || true
fi

echo "Starting: $*"
exec "$@"
