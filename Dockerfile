# Этап 1: Базовый образ с кэшированием зависимостей
FROM python:3.12-slim AS base

# Установка необходимых системных пакетов
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

# Установка non-root пользователя
RUN groupadd -r botuser && useradd -r -g botuser -d /app -s /sbin/nologin botuser

# Рабочая директория
WORKDIR /app

# Сначала копируем только requirements для кэширования слоя
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копируем остальной код приложения
COPY . .

# Переключаемся на non-root пользователя
USER botuser

# Запуск приложения
CMD ["python", "main.py"]
