FROM python:3.11-slim

WORKDIR /app

# Копирование и установка зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование кода
COPY . .

# Создание директорий для хранения файлов
RUN mkdir -p storage/ttl_media

# Экспорт порта для webhook
EXPOSE 8443

# Команда запуска
CMD ["python", "main.py"]