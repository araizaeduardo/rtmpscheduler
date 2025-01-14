# Usar una imagen base de Ubuntu
FROM ubuntu:22.04

# Evitar interacciones durante la instalación
ENV DEBIAN_FRONTEND=noninteractive

# Variables de entorno
ENV APP_HOME=/app
ENV PYTHONUNBUFFERED=1
ENV NGINX_VERSION=1.24.0
ENV NGINX_RTMP_VERSION=1.2.2
ENV TZ=America/Los_Angeles

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y \
    python3.10 \
    python3-pip \
    python3-venv \
    ffmpeg \
    supervisor \
    wget \
    curl \
    build-essential \
    libpcre3 \
    libpcre3-dev \
    libssl-dev \
    zlib1g-dev \
    tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

# Crear directorio de la aplicación
WORKDIR $APP_HOME

# Copiar requirements.txt primero para aprovechar la caché de Docker
COPY requirements.txt .

# Crear y activar entorno virtual
RUN python3 -m venv venv && \
    . venv/bin/activate && \
    pip install --no-cache-dir -r requirements.txt

# Copiar el resto de los archivos de la aplicación
COPY . .

# Compilar e instalar Nginx con módulo RTMP
RUN cd /tmp && \
    wget http://nginx.org/download/nginx-${NGINX_VERSION}.tar.gz && \
    wget https://github.com/arut/nginx-rtmp-module/archive/v${NGINX_RTMP_VERSION}.tar.gz && \
    tar -zxf nginx-${NGINX_VERSION}.tar.gz && \
    tar -zxf v${NGINX_RTMP_VERSION}.tar.gz && \
    cd nginx-${NGINX_VERSION} && \
    ./configure \
        --prefix=/usr/local/nginx \
        --with-http_ssl_module \
        --with-http_stub_status_module \
        --add-module=../nginx-rtmp-module-${NGINX_RTMP_VERSION} && \
    make && \
    make install && \
    rm -rf /tmp/*

# Copiar configuraciones
COPY nginx.conf /usr/local/nginx/conf/nginx.conf
COPY rtmp-streamer.conf /etc/supervisor/conf.d/

# Crear directorios necesarios
RUN mkdir -p /var/log/nginx && \
    mkdir -p /var/log/supervisor && \
    mkdir -p /var/log/gunicorn && \
    mkdir -p $APP_HOME/uploads/receiving && \
    mkdir -p $APP_HOME/instance && \
    mkdir -p $APP_HOME/static

# Establecer permisos
RUN chown -R www-data:www-data $APP_HOME && \
    chmod -R 755 $APP_HOME && \
    chown -R www-data:www-data /var/log/nginx && \
    chown -R www-data:www-data /var/log/supervisor && \
    chown -R www-data:www-data /var/log/gunicorn

# Copiar script de inicio
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Usuario no root
USER www-data

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Exponer puertos
EXPOSE 80 1935 8080

# Comando de inicio
ENTRYPOINT ["docker-entrypoint.sh"]
