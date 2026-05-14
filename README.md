<p align="center">
  <img src="https://img.shields.io/badge/Python-3.9+-3776AB?style=for-the-badge&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/Flask-3.1-000000?style=for-the-badge&logo=flask&logoColor=white" />
  <img src="https://img.shields.io/badge/MongoDB-Atlas-47A248?style=for-the-badge&logo=mongodb&logoColor=white" />
  <img src="https://img.shields.io/badge/Mistral-AI-FF6F00?style=for-the-badge&logo=ai&logoColor=white" />
  <img src="https://img.shields.io/badge/Gemini-API-4285F4?style=for-the-badge&logo=google&logoColor=white" />
</p>

# 🏛️ AmbaNotes Engine

> **Backend cerdas berbasis AI untuk manajemen dan analisis dokumen surat — dibangun dengan arsitektur microservices menggunakan Flask.**

AmbaNotes Engine adalah sistem backend yang melayani berbagai fitur **Artificial Intelligence** dan **manajemen dokumen** untuk aplikasi AmbaNotes. Sistem ini mampu melakukan klasifikasi surat secara otomatis, ekstraksi teks dari gambar (OCR), pengenalan entitas (NER), ringkasan dokumen, dan masih banyak lagi.

---

## 📐 Arsitektur Sistem

Aplikasi ini menggunakan pola **API Gateway** dengan **Flask Blueprints**, di mana seluruh microservices diorkestrasi melalui satu entry point yang berjalan di port `5009`.

```
                        ┌─────────────────────────┐
                        │      Client / App        │
                        │    (Flutter Mobile)      │
                        └────────────┬────────────┘
                                     │
                                     ▼
                        ┌─────────────────────────┐
                        │   🌐 API Gateway        │
                        │   Flask (port 5009)     │
                        │   + Swagger/Flasgger    │
                        └────────────┬────────────┘
                                     │
          ┌──────────────────────────┼──────────────────────────┐
          │              │           │           │              │
          ▼              ▼           ▼           ▼              ▼
   ┌────────────┐ ┌────────────┐ ┌────────┐ ┌────────────┐ ┌────────┐
   │ 🔐 Auth    │ │ 📄 Document│ │ 🤖 AI  │ │ 📊 Insight │ │ 🔔 Notif│
   │  Service   │ │  Service   │ │ Service│ │  Service   │ │ Service │
   └────────────┘ └────────────┘ └────────┘ └────────────┘ └────────┘
          │              │           │           │
          ▼              ▼           ▼           ▼
   ┌────────────┐ ┌────────────┐ ┌────────┐ ┌────────────┐
   │ 🏷️ NER     │ │ 👁️ OCR     │ │📋 Class│ │ ⏰ Reminder│
   │  Service   │ │  Service   │ │Service │ │  Service   │
   └────────────┘ └────────────┘ └────────┘ └────────────┘
          │              │           │
          ▼              ▼           ▼
   ┌─────────────────────────────────────────┐
   │          🗄️ MongoDB Atlas               │
   │    (users, documents, organizations)    │
   └─────────────────────────────────────────┘
```

---

## ✨ Fitur Utama

| Fitur | Deskripsi | Teknologi |
|:------|:----------|:----------|
| 🔐 **Autentikasi** | Registrasi, login, manajemen organisasi (Invitation System & RBAC) | JWT + Werkzeug |
| 📄 **Manajemen Dokumen** | Upload, simpan, dan kelola file dokumen surat | MongoDB GridFS |
| 📋 **Klasifikasi Surat** | Klasifikasi otomatis jenis surat (Undangan, Permohonan, Tugas, Keputusan, Edaran) | HuggingFace Transformers + SafeTensors |
| 👁️ **OCR** | Ekstraksi teks dari gambar dokumen | Google Gemini API |
| 🏷️ **Named Entity Recognition** | Ekstraksi entitas (Nama, Lokasi, Organisasi) dari teks bahasa Indonesia | IndoBERT (`cahya/bert-base-indonesian-NER`) |
| 🤖 **AI Assistant** | Ringkasan dokumen otomatis dan chatbot kontekstual | Mistral AI API |
| 📊 **Insight & Analitik** | Analisis data dan tren dari koleksi dokumen | Pandas + NLTK |
| ⏰ **Reminder** | Penjadwalan dan pengelolaan pengingat | Flask Blueprint |
| 🔔 **Notifikasi** | Sistem notifikasi terintegrasi | Flask Blueprint |

---

## 🛠️ Tech Stack

| Layer | Teknologi |
|:------|:----------|
| **Framework** | Flask 3.1, Flask Blueprints |
| **Database** | MongoDB Atlas (PyMongo) |
| **Authentication** | PyJWT, Werkzeug Security |
| **AI / ML** | HuggingFace Transformers, PyTorch, SafeTensors |
| **NLP** | IndoBERT (NER), NLTK, Sentencepiece |
| **OCR** | Google Gemini API (Multimodal) |
| **LLM** | Mistral AI API |
| **API Docs** | Flasgger (Swagger UI) |
| **Data Processing** | Pandas, NumPy |
| **Environment** | python-dotenv |

---

## 📁 Struktur Proyek

```
ambanotes-engine/
├── api_gateway/            # 🌐 Entry point & routing utama
│   └── api.py
├── auth_service/           # 🔐 Autentikasi & manajemen user/org
│   └── auth_service.py
├── document_service/       # 📄 Manajemen dokumen
│   └── document_service.py
├── classification_service/ # 📋 Klasifikasi jenis surat (ML)
│   └── classification_service.py
├── ocr_service/            # 👁️ Optical Character Recognition
│   └── ocr_service.py
├── ner_service/            # 🏷️ Named Entity Recognition
│   └── ner_service.py
├── ai_service/             # 🤖 Summarization & Chatbot
│   └── ai_service.py
├── insight_service/        # 📊 Analitik & insight data
│   ├── insight_service.py
│   ├── services/
│   │   ├── analytics_service.py
│   │   └── mongo_service.py
│   └── utils/
│       └── text_cleaner.py
├── reminder_service/       # ⏰ Pengingat
│   └── reminder.py
├── notification_service/   # 🔔 Notifikasi
│   └── notif.py
├── common/                 # 🔧 Shared utilities
│   ├── config.py           #    Konfigurasi environment
│   ├── db.py               #    Koneksi MongoDB
│   ├── jwt_utils.py        #    Generate & verify JWT
│   └── logger.py           #    Centralized logging
├── models/                 # 🧠 Model ML lokal (gitignored)
│   └── surat_model/        #    Model klasifikasi surat
├── .env.example            # 📝 Template environment variables
├── requirements.txt        # 📦 Python dependencies
└── README.md
```

---

## 🚀 Panduan Instalasi

### Prasyarat

- **Python 3.9** atau lebih baru
- **pip** (Python package manager)
- Koneksi internet (untuk MongoDB Atlas, Mistral AI, dan Gemini API)
- API Key: **Mistral AI** dan **Google Gemini**

### 1️⃣ Clone Repository

```bash
git clone https://github.com/<username>/ambanotes-engine.git
cd ambanotes-engine
```

### 2️⃣ Buat & Aktifkan Virtual Environment

```bash
# Buat virtual environment
python -m venv venv

# Aktifkan (Windows)
venv\Scripts\activate

# Aktifkan (Mac/Linux)
source venv/bin/activate
```

### 3️⃣ Install Dependencies

```bash
pip install -r requirements.txt
```

### 4️⃣ Konfigurasi Environment Variables

Salin file template dan isi dengan kredensial Anda:

```bash
cp .env.example .env
```

Kemudian edit file `.env`:

```env
# ─── Database ──────────────────────────────────────
MONGO_URI="mongodb+srv://<username>:<password>@cluster0.mongodb.net/ambanotes?retryWrites=true&w=majority"
DB_NAME="ambanotes"

# ─── Authentication ────────────────────────────────
JWT_SECRET_KEY="ganti-dengan-secret-key-yang-aman"

# ─── AI Services ───────────────────────────────────
MISTRAL_API_KEY="your-mistral-api-key"
GEMINI_API_KEY="your-gemini-api-key"

# ─── Flask ─────────────────────────────────────────
FLASK_APP="api_gateway/api.py"
FLASK_ENV="development"
FLASK_DEBUG="1"
PORT="5009"
```

### 5️⃣ Siapkan Model ML (Opsional)

Jika menggunakan fitur klasifikasi surat, letakkan file model di:

```
models/surat_model/
├── config.json
├── model.safetensors
├── tokenizer_config.json
├── vocab.txt
└── special_tokens_map.json
```

> ⚠️ **Catatan:** File model berukuran besar dan **tidak disertakan** di repository (gitignored). Unduh atau salin model secara manual jika melakukan clone baru.

### 6️⃣ Jalankan Server

```bash
python api_gateway/api.py
```

Server akan berjalan di:

```
🌐 http://localhost:5009
📖 http://localhost:5009/apidocs  (Swagger UI)
```

---

## 📡 API Endpoints

### Gateway

| Method | Endpoint | Deskripsi |
|:-------|:---------|:----------|
| `GET` | `/` | Status server |
| `GET` | `/health` | Health check gateway |

### 🔐 Auth Service (`/auth`)

| Method | Endpoint | Deskripsi |
|:-------|:---------|:----------|
| `POST` | `/auth/register` | Registrasi user baru (create/join org) |
| `POST` | `/auth/login` | Login & dapatkan JWT token |
| `DELETE` | `/auth/members/<id>` | Hapus member (Role: Admin) |
| `POST` | `/auth/invite` | Kirim undangan ke email (Role: Owner) |
| `GET` | `/auth/invitations` | Lihat daftar undangan masuk |
| `POST` | `/auth/invitations/<id>/accept` | Terima undangan bergabung |
| `POST` | `/auth/invitations/<id>/reject` | Tolak undangan bergabung |
| `GET` | `/auth/health` | Health check auth service |

### 📄 Document Service (`/document`)

| Method | Endpoint | Deskripsi |
|:-------|:---------|:----------|
| `POST` | `/document/upload` | Upload dokumen |
| `GET` | `/document/list` | Daftar semua dokumen |
| `GET` | `/document/<id>` | Detail dokumen berdasarkan ID |

### 📋 Classification Service (`/classification`)

| Method | Endpoint | Deskripsi |
|:-------|:---------|:----------|
| `POST` | `/classification/predict` | Klasifikasi jenis surat (Hybrid: local/gemini) |

### 👁️ OCR Service (`/ocr`)

| Method | Endpoint | Deskripsi |
|:-------|:---------|:----------|
| `POST` | `/ocr/extract-text` | Ekstraksi teks dari gambar (multipart/form-data) |

### 🏷️ NER Service (`/ner`)

| Method | Endpoint | Deskripsi |
|:-------|:---------|:----------|
| `POST` | `/ner/extract` | Ekstraksi entitas (nama, lokasi, organisasi) |
| `GET` | `/ner/health` | Health check NER service |

### 🤖 AI Service (`/ai`)

| Method | Endpoint | Deskripsi |
|:-------|:---------|:----------|
| `POST` | `/ai/summarize` | Ringkasan dokumen otomatis |
| `POST` | `/ai/chat` | Chatbot kontekstual |

### 📊 Insight Service (`/insight`)

| Method | Endpoint | Deskripsi |
|:-------|:---------|:----------|
| `GET` | `/insight/` | Home insight API |
| `GET` | `/insight/api/insights` | Data insight & analitik |

### ⏰ Reminder Service (`/reminder`)

| Method | Endpoint | Deskripsi |
|:-------|:---------|:----------|
| — | `/reminder/...` | Endpoint pengingat |

### 🔔 Notification Service (`/notification`)

| Method | Endpoint | Deskripsi |
|:-------|:---------|:----------|
| — | `/notification/...` | Endpoint notifikasi |

> 💡 **Tip:** Untuk dokumentasi interaktif lengkap beserta request/response schema, buka **Swagger UI** di `http://localhost:5009/apidocs` saat server berjalan.

---

## 🧪 Contoh Penggunaan API

### Login

```bash
curl -X POST http://localhost:5009/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "user123", "password": "password123"}'
```

### Klasifikasi Surat

```bash
curl -X POST http://localhost:5009/classification/predict \
  -H "Content-Type: application/json" \
  -d '{"text": "Dengan hormat, kami mengundang Bapak/Ibu untuk menghadiri rapat..."}'
```

### OCR (Ekstraksi Teks dari Gambar)

```bash
curl -X POST http://localhost:5009/ocr/extract-text \
  -F "file=@surat_undangan.png"
```

### NER (Ekstraksi Entitas)

```bash
curl -X POST http://localhost:5009/ner/extract \
  -H "Content-Type: application/json" \
  -d '{"text": "Bima Arya dari Universitas Amikom Purwokerto akan menghadiri seminar di Jakarta."}'
```

### AI Summarize

```bash
curl -X POST http://localhost:5009/ai/summarize \
  -H "Content-Type: application/json" \
  -d '{"text": "Isi dokumen surat yang panjang..."}'
```

---

## 🗄️ Skema Database (MongoDB)

| Collection | Deskripsi | Field Utama |
|:-----------|:----------|:------------|
| `users` | Data pengguna | `username`, `password`, `role`, `org_id` |
| `organizations` | Data organisasi | `name`, `invitation_code`, `created_at` |
| `documents` | Dokumen tersimpan | `title`, `content`, `type`, `org_id` |
| `logs` | Log aktivitas sistem | `service`, `message`, `timestamp` |
| `invitations` | Data undangan | `email`, `org_id`, `status`, `role` |

---

## 📝 Catatan Pengembangan

- **Logging Terpusat** — Seluruh service menggunakan fungsi `log_event()` dari `common/logger.py` untuk konsistensi pencatatan log.
- **Konfigurasi Terpusat** — Semua environment variable dikelola melalui `common/config.py` menggunakan `python-dotenv`.
- **Model ML Lokal** — File model `.safetensors` di folder `models/` berukuran besar dan tidak di-push ke GitHub. Pastikan untuk menyalin file model secara manual setelah clone.
- **IndoBERT NER** — Model `cahya/bert-base-indonesian-NER` diunduh otomatis dari HuggingFace Hub saat pertama kali dijalankan.
- **OCR via Gemini** — OCR menggunakan Google Gemini API (multimodal) untuk akurasi tinggi, menggantikan Tesseract.

---

## 👥 Tim Pengembang

Proyek ini dikembangkan sebagai bagian dari **Capstone Project Semester 6**.

---

<p align="center">
  <sub>Built with ❤️ using Flask, MongoDB, and AI</sub>
</p>
