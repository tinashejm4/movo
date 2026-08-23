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

# Start Django's development server.
# echo "Starting Django runserver on port ${PORT:-8000}..."
# exec python manage.py runserver 0.0.0.0:${PORT:-8000}

# Start Daphne server for production.
echo "Starting Daphne on port ${PORT:-8000}..."
exec daphne -b 0.0.0.0 -p ${PORT:-8000} Movo.asgi:application