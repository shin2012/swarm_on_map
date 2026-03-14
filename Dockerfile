FROM python:3.10-slim

WORKDIR /app

# Install system dependencies if any
RUN apt-get update && apt-get install -y \
    gcc \
    libmariadb-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Set environment variables (defaults)
ENV FLASK_APP=app.py
ENV FLASK_ENV=production
ENV DB_HOST=mariadb
ENV DB_USER=
ENV DB_PASSWORD=
ENV DB_DATABASE=
ENV DB_PORT=3306

EXPOSE 5005

CMD ["python", "app.py"]
