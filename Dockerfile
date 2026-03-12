FROM python:3.11-slim

LABEL maintainer="SnappsiSnappes 42leonid@gmail.com"
LABEL description="Mumble Music Bot with Python"

# Системные зависимости
RUN apt-get update && apt-get install -y --no-install-recommends \
    libopus0 ffmpeg git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Устанавливаем Python-зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копируем исходный код (всю папку src)
COPY src/ /app/src/

# Создаём папки для томов
RUN mkdir -p /app/certs /app/music /app/logs

# Запускаем бота из папки src
CMD ["python", "/app/src/bot.py"]