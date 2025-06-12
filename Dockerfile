# Gunakan image Python resmi sebagai base image
FROM python:3.9-slim-buster

# Instal FFmpeg dan dependensi lainnya
# slim-buster based images uses apt-get
RUN apt-get update && apt-get install -y ffmpeg libsm6 libxext6 && \
    rm -rf /var/lib/apt/lists/*

# Atur direktori kerja di dalam container
WORKDIR /app

# Salin requirements.txt dan instal dependensi Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Salin sisa kode aplikasi
COPY . .

# Buat folder uploads jika belum ada (untuk pengembangan lokal/jika diperlukan di server ephemeral)
RUN mkdir -p uploads

# Ekspos port yang digunakan aplikasi Flask (default: 5000)
EXPOSE 5000

# Perintah untuk menjalankan aplikasi menggunakan Gunicorn
# Gunicorn akan berjalan pada port yang ditentukan oleh Railway (PORT environment variable)
CMD ["gunicorn", "--bind", "0.0.0.0:$PORT", "app:app"] 