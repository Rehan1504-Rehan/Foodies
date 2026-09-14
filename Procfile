release: python manage.py migrate --no-input
web: gunicorn foodies.wsgi:application --bind 0.0.0.0:$PORT --workers 3 --timeout 120
