#!/bin/sh
set -e

echo "[entrypoint] applying migrations (mysql: default)"
python manage.py migrate --noinput --database=default
echo "[entrypoint] applying migrations (postgres: vector)"
python manage.py migrate --noinput --database=vector

exec "$@"
