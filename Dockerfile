FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .


COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh


RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app

RUN chown appuser:appuser /entrypoint.sh

USER appuser

EXPOSE 8000

CMD ["/entrypoint.sh"]