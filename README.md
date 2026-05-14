# AmbaNotes Engine

AmbaNotes Engine adalah sistem *backend* berbasis **Flask** yang bertugas melayani berbagai fitur cerdas (AI) dan manajemen dokumen untuk aplikasi AmbaNotes. 

Arsitektur aplikasi ini menggunakan pola **API Gateway dengan Flask Blueprints**, di mana berbagai *microservices* (seperti Klasifikasi Surat, OCR, Named Entity Recognition, Notifikasi, dsb) digabungkan menjadi satu proses *router* utama yang berjalan di port `5009`.

## Daftar Layanan (Services)

Berikut adalah daftar *service* yang terintegrasi di dalam engine ini:
* **AI Service** (`/ai`) - Melakukan analisa, ringkasan, dan ekstraksi entitas menggunakan Mistral AI.
* **Auth Service** (`/auth`) - Mengelola proses autentikasi.
* **Classification Service** (`/classification`) - Mengklasifikasikan jenis dokumen (menggunakan model safetensor lokal).
* **Document Service** (`/document`) - Manajemen file dokumen.
* **Insight Service** (`/insight`) - Menyediakan analitik data.
* **NER Service** (`/ner`) - Mengekstraksi entitas dari teks.
* **OCR Service** (`/ocr`) - Membaca teks dari gambar (Optical Character Recognition).
* **Reminder Service** (`/reminder`) - Menjadwalkan dan mengelola pengingat.
* **Notification Service** (`/notification`) - Menangani notifikasi.

---

## Persyaratan Sistem

Sebelum menjalankan aplikasi, pastikan Anda memiliki:
1. **Python 3.9+** terinstal di perangkat Anda.
2. Lingkungan virtual (*Virtual Environment*).
3. Koneksi internet (untuk mengunduh *library* dan mengakses API eksternal seperti Mistral dan MongoDB Atlas).

---

## Panduan Instalasi dan Menjalankan (Setup Guide)

### 1. Buat Virtual Environment
Di direktori utama project, jalankan:
```bash
python -m venv venv
```

### 2. Aktifkan Virtual Environment
* **Windows**:
  ```bash
  venv\Scripts\activate
  ```
* **Mac/Linux**:
  ```bash
  source venv/bin/activate
  ```

### 3. Install Dependencies
Jalankan perintah berikut untuk menginstal semua pustaka yang dibutuhkan:
```bash
pip install -r requirements.txt
```

### 4. Konfigurasi Environment Variables (`.env`)
Aplikasi ini memerlukan beberapa kredensial agar dapat berjalan. 
1. Buat file bernama `.env` di direktori utama (root).
2. Anda bisa merujuk ke file `.env.example` sebagai panduan.
3. Isi file `.env` dengan format berikut:
   ```env
   # Koneksi MongoDB Atlas
   MONGO_URI="mongodb+srv://<username>:<password>@<cluster>.mongodb.net/?retryWrites=true&w=majority"
   DB_NAME="ambanotes"

   # Secret Key untuk Token Authentication
   JWT_SECRET_KEY="super-secret-key-anda"

   # Mistral AI (jika menggunakan fitur AI)
   MISTRAL_API_KEY="kunci-api-mistral-anda"
   ```

### 5. Jalankan API Gateway
Jalankan file *entry point* utama aplikasi:
```bash
python api_gateway/api.py
```
Aplikasi akan berjalan di `http://0.0.0.0:5009`.

---

## Dokumentasi API (Swagger / Flasgger)

Seluruh *endpoint* dari berbagai layanan telah didokumentasikan secara otomatis menggunakan **Flasgger**. Saat aplikasi sudah berjalan, Anda bisa membuka browser dan melihat UI Swagger di:

👉 **http://localhost:5009/apidocs**

Dari halaman tersebut, Anda bisa melihat parameter yang dibutuhkan dan menguji coba (Test) API secara langsung.

---

## Catatan Tambahan (Pengembangan)

* File model cerdas AI lokal yang berada di folder `models/` berukuran besar dan **tidak ikut dipush** ke GitHub (sudah diatur di `.gitignore`). Pastikan Anda menaruh file model `.safetensors` secara manual jika melakukan clone di komputer baru.
* Semua fungsi *logging* menggunakan fungsi terpusat `log_event()` yang ada di `common/logger.py`.
