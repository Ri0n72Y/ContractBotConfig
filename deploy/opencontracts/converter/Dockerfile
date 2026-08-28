FROM python:3.12-alpine

WORKDIR /app

RUN pip install --no-cache-dir "flask>=3,<4" "httpx>=0.27,<1" \
    && addgroup -S app \
    && adduser -S -G app app

COPY app.py /app/app.py

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

USER app
EXPOSE 8080

CMD ["python", "/app/app.py"]
