#!/bin/bash
set -e

echo "Running checks"
python manage.py check

echo "Running Django migrations..."
python manage.py migrate --noinput

exec "$@"
