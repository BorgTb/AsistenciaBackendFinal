# Imagen base
FROM python:3.11-slim

WORKDIR /app

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y \
    cmake \
    g++ \
    libopenblas-dev \
    liblapack-dev \
    libboost-all-dev \
    libjpeg-dev \
    libpng-dev \
    libx11-dev \
    && rm -rf /var/lib/apt/lists/*

# Copiar dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código
COPY app.py .

# Crear carpetas para imágenes y rostros
RUN mkdir /app/imagenes /app/rostros

CMD ["python", "-u", "app.py"]