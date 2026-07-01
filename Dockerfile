FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt /tmp/requirements.txt
RUN pip install --upgrade pip && pip install -r /tmp/requirements.txt

COPY backend/ /app/

FROM base AS assets

RUN python manage.py collectstatic --noinput

EXPOSE 8241

CMD ["python", "-m", "http.server", "8241", "--directory", "/app/staticfiles"]


FROM base AS app

EXPOSE 8000

CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py shell -c \"import os;from django.contrib.auth import get_user_model;U=get_user_model();u=os.getenv('DJANGO_SUPERUSER_USERNAME');p=os.getenv('DJANGO_SUPERUSER_PASSWORD');e=os.getenv('DJANGO_SUPERUSER_EMAIL','admin@example.com');(u and p and not U.objects.filter(username=u).exists()) and U.objects.create_superuser(u,e,p)\" && gunicorn fifa.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 120"]
