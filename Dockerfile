# Menggunakan Python 3.9 slim sebagai base image untuk ukuran yang lebih kecil
FROM python:3.9-slim-buster

# Mengatur working directory di dalam container
WORKDIR /app

# Menginstal FFmpeg dan dependensi lain yang diperlukan
# FFmpeg diperlukan untuk operasi konversi video
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsm6 \
    libxext6 \
    && rm -rf /var/lib/apt/lists/*

# Menyalin requirements.txt dan menginstal dependensi Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Menyalin sisa kode aplikasi ke dalam container
COPY . .

# Mengatur variabel lingkungan untuk Flask
ENV FLASK_APP=app.py
ENV FLASK_ENV=production

# Membuka port 5000 (port default untuk Gunicorn di Heroku)
EXPOSE 5000

# Menjalankan aplikasi menggunakan Gunicorn (sesuai dengan Procfile)
# Perintah ini akan dioverride oleh Procfile di Heroku, tapi ini adalah default yang baik
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"] 