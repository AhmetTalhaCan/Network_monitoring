#!/bin/bash

# Çevresel değişkenleri ayarla
export FLASK_APP=server.main:app  # Flask uygulamanızın dosya adı (örneğin, server.main.py)
export FLASK_ENV=production  # Flask ortamını üretim olarak ayarla

# Render platformu için doğru portu kullan
PORT=${PORT:-5000}  # Render, PORT değişkenini dinamik olarak sağlar, eğer tanımlı değilse 5000 kullan

# Gunicorn ile Flask uygulamasını başlat
gunicorn -w 4 server.main:app --bind 0.0.0.0:$PORT
