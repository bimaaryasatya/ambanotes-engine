<p align="center">
  <img src="https://img.shields.io/badge/Python-3.9+-3776AB?style=for-the-badge&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/Flask-3.1-000000?style=for-the-badge&logo=flask&logoColor=white" />
  <img src="https://img.shields.io/badge/MongoDB-Atlas-47A248?style=for-the-badge&logo=mongodb&logoColor=white" />
  <img src="https://img.shields.io/badge/Mistral-AI-FF6F00?style=for-the-badge&logo=ai&logoColor=white" />
  <img src="https://img.shields.io/badge/Gemini-API-4285F4?style=for-the-badge&logo=google&logoColor=white" />
  <img src="https://img.shields.io/badge/IndoBERT-NER-E91E63?style=for-the-badge&logo=huggingface&logoColor=white" />
</p>

# 🏛️ AmbaNotes Engine

> **Backend cerdas berbasis AI untuk manajemen dan analisis dokumen surat di lingkungan pemerintahan & enterprise — dibangun dengan arsitektur microservices menggunakan Flask.**

AmbaNotes Engine adalah sistem backend yang melayani berbagai fitur **Artificial Intelligence** dan **manajemen dokumen** untuk aplikasi AmbaNotes. Sistem ini mampu melakukan klasifikasi surat secara otomatis, ekstraksi teks dari gambar (OCR), pengenalan entitas (NER), ringkasan dokumen, disposisi cerdas, hingga otomatisasi pembuatan surat resmi (Surat Tugas) dengan kop surat dan tanda tangan digital.

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
          ┌──────────┬───────────┬───┴────┬───────────┬──────────┐
          ▼          ▼           ▼        ▼           ▼          ▼
   ┌───────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
   │ 🔐 Auth   │ │📄 Doc  │ │🤖 AI   │ │📊 Ins. │ │🏗️ Gen  │ │⏰ Rem. │
   │ +Delegasi │ │Service │ │Jarvis  │ │Service │ │Service │ │Service │
   └─────┬─────┘ └───┬────┘ └────────┘ └────────┘ └────────┘ └────────┘
         │            │
         │            ├──────────┬──────────┐
         │            ▼          ▼          ▼
         │     ┌───────────┐ ┌────────┐ ┌────────┐
         │     │ 👁️ OCR    │ │📋 Class│ │🏷️ NER  │
         │     │ (Gemini)  │ │(Local) │ │(BERT)  │
         │     └───────────┘ └────────┘ └────────┘
         │
         ▼
   ┌─────────────────────────────────────────┐
   │          🗄️ MongoDB Atlas               │
   │  users · documents · organizations      │
   │  delegations · assets · reminders       │
   │  invitations · logs                     │
   └─────────────────────────────────────────┘
```

---

## ✨ Fitur Utama

### 🤖 AI Intelligence (Jarvis)
| Fitur | Deskripsi |
|:------|:----------|
| **Semantic Search** | Pencarian dokumen berdasarkan makna/konteks, bukan hanya kata kunci |
| **Global Chatbot** | Tanya jawab AI yang menganalisis seluruh dokumen organisasi dengan citasi |
| **Smart Disposition** | AI menyarankan unit/dinas mana yang paling tepat menangani surat masuk |
| **Voice Intent** | Mengubah perintah suara menjadi aksi terstruktur (buat surat, cari dokumen, dll.) |
| **Auto-Reminder** | Ekstraksi otomatis agenda/tugas dari isi surat ke format JSON |
| **Smart Reply Draft** | Pembuatan 3 opsi draf balasan surat formal (setuju, tolak, netral) |
| **Smart Redaction** | Sensor otomatis data sensitif (NIK, No. HP, Alamat) sesuai UU PDP |
| **Document Translation** | Terjemahan teks ke Bahasa Indonesia formal kedinasan |
| **Conflict Detection** | Mendeteksi konflik jadwal atau aturan antara surat baru dengan agenda eksisting |
| **Budget Extractor** | Ekstraksi otomatis nilai nominal uang dan tujuan anggaran dari teks surat |
| **Workflow Automation** | Saran aksi otomatis (Calendar/Reminder) berdasarkan isi surat |
| **Predictive Analytics** | Prediksi beban kerja organisasi 3 bulan ke depan berdasarkan tren administrasi |
| **Priority Intelligence** | Analisis sentimen, tingkat urgensi (High/Low), dan auto-tagging (#hashtag) |



### 🏢 Enterprise & Delegasi
| Fitur | Deskripsi |
|:------|:----------|
| **Multi-Delegasi** | Organisasi dibagi menjadi unit/dinas (misal: Dinas PU, Dinas Sosial) |
| **Mutasi Pegawai** | Owner dapat memindahkan pegawai antar unit beserta seluruh dokumennya |
| **Kop Surat Digital** | Upload kop surat per unit untuk digunakan dalam generator dokumen |
| **Tanda Tangan Digital** | Upload TTD/QR Code per unit (hanya oleh Owner) |
| **Surat Tugas Generator** | Generate surat resmi HTML lengkap dengan kop, nomor surat, dan TTD |
| **Anti-Fraud Verify** | Sidik jari digital (hash) untuk memverifikasi keaslian surat yang di-generate |


### 📄 Document Processing Pipeline
| Fitur | Deskripsi |
|:------|:----------|
| **OCR** | Ekstraksi teks dari gambar dokumen menggunakan Google Gemini API |
| **Klasifikasi** | Klasifikasi otomatis jenis surat (Undangan, Permohonan, Tugas, dll.) |
| **NER** | Pengenalan entitas (Nama, Lokasi, Organisasi) berbahasa Indonesia |
| **Auto-Pipeline** | Upload → OCR → Klasifikasi → NER dijalankan otomatis dalam satu request |

---

## 🛠️ Tech Stack

| Layer | Teknologi |
|:------|:----------|
| **Framework** | Flask 3.1, Flask Blueprints |
| **Database** | MongoDB Atlas (PyMongo) |
| **Authentication** | PyJWT, Werkzeug Security |
| **AI / ML** | HuggingFace Transformers, PyTorch, SafeTensors |
| **NLP** | IndoBERT (`cahya/bert-base-indonesian-NER`), NLTK |
| **OCR** | Google Gemini API (Multimodal Vision) |
| **LLM** | Mistral AI API (`mistral-small`) |
| **API Docs** | Flasgger (Swagger UI) |
| **Data Processing** | Pandas, NumPy |
| **Template Engine** | Jinja2 (untuk generator surat) |
| **Environment** | python-dotenv |

---

## 📁 Struktur Proyek

```
ambanotes-engine/
├── api_gateway/                # 🌐 Entry point & routing utama
│   └── api.py                  #    Registrasi seluruh Blueprint
├── auth_service/               # 🔐 Autentikasi & Enterprise
│   └── auth_service.py         #    Register, Login, Delegasi, Asset, Mutasi
├── document_service/           # 📄 Manajemen dokumen
│   └── document_service.py     #    Upload, List, Delete, Replace (+ auto-pipeline)
├── classification_service/     # 📋 Klasifikasi surat
│   └── classification_service.py  # Hybrid: Local SafeTensors / Gemini fallback
├── ocr_service/                # 👁️ Optical Character Recognition
│   └── ocr_service.py          #    Multimodal via Google Gemini API
├── ner_service/                # 🏷️ Named Entity Recognition
│   └── ner_service.py          #    IndoBERT cahya/bert-base-indonesian-NER
├── ai_service/                 # 🤖 AI Jarvis Intelligence
│   └── ai_service.py           #    Summarize, Chat, Search, Redact, Disposition, Voice
├── insight_service/            # 📊 Analitik & Weekly Summary
│   ├── insight_service.py
│   ├── services/
│   │   ├── analytics_service.py
│   │   └── mongo_service.py
│   └── utils/
│       └── text_cleaner.py
├── reminder_service/           # ⏰ Manajemen Pengingat
│   └── reminder.py
├── generator_service/          # 🏗️ Document Generator (Surat Tugas)
│   └── generator.py
├── notification_service/       # 🔔 Notifikasi (placeholder)
│   └── notif.py
├── common/                     # 🔧 Shared utilities
│   ├── config.py               #    Environment variables
│   ├── db.py                   #    MongoDB connection & collections
│   ├── jwt_utils.py            #    Token generate/verify + RBAC decorators
│   └── logger.py               #    Centralized audit logging
├── models/                     # 🧠 Model ML lokal (gitignored)
│   └── surat_model/            #    config.json, model.safetensors, tokenizer, vocab
├── .env.example                # 📝 Template environment variables
├── requirements.txt            # 📦 Python dependencies
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
GATEWAY_URL="http://localhost:5009"

# ─── Email (SMTP) ──────────────────────────────────
MAIL_SERVER="smtp.gmail.com"
MAIL_PORT=587
MAIL_USE_TLS="True"
MAIL_USERNAME="your-email@gmail.com"
MAIL_PASSWORD="your-app-password"
MAIL_DEFAULT_SENDER="AmbaNotes <your-email@gmail.com>"
```

### 5️⃣ Siapkan Model ML (Opsional)

Jika menggunakan fitur klasifikasi surat lokal, letakkan file model di:

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

---

### 🔐 Auth Service (`/auth`)

| Method | Endpoint | Deskripsi | Auth | Role |
|:-------|:---------|:----------|:-----|:-----|
| `POST` | `/auth/register` | Registrasi user baru (create/join org) | ❌ | — |
| `POST` | `/auth/login` | Login & dapatkan JWT token | ❌ | — |
| `GET` | `/auth/profile` | Lihat profil user yang sedang login | ✅ | Any |
| `POST` | `/auth/change-password` | Ganti password (saat login) | ✅ | Any |
| `POST` | `/auth/forgot-password` | Request OTP reset password via email | ❌ | — |
| `POST` | `/auth/reset-password` | Reset password menggunakan kode OTP | ❌ | — |
| `POST` | `/auth/invite` | Undang member baru via email | ✅ | Owner |
| `GET` | `/auth/health` | Health check auth service | ❌ | — |

---

### 🏢 Enterprise / Delegasi (`/auth`)

| Method | Endpoint | Deskripsi | Auth | Role |
|:-------|:---------|:----------|:-----|:-----|
| `POST` | `/auth/delegations` | Buat unit/dinas baru | ✅ | Owner |
| `GET` | `/auth/delegations` | List semua unit dalam organisasi | ✅ | Any |
| `POST` | `/auth/change-delegation` | Mutasi pegawai ke unit lain | ✅ | Owner |
| `POST` | `/auth/assets` | Upload kop surat / TTD digital | ✅ | Owner |

---

### 📄 Document Service (`/document`)

| Method | Endpoint | Deskripsi | Auth | Role |
|:-------|:---------|:----------|:-----|:-----|
| `POST` | `/document/upload` | Upload dokumen (auto: OCR → Classify → NER) | ✅ | Any |
| `GET` | `/document/list` | List semua dokumen organisasi | ✅ | Any |
| `DELETE` | `/document/<doc_id>` | Hapus dokumen | ✅ | Owner |
| `PUT` | `/document/replace/<doc_id>` | Ganti & proses ulang dokumen | ✅ | Any |
| `GET` | `/document/health` | Health check document service | ❌ | — |

---

### 📋 Classification Service (`/classification`)

| Method | Endpoint | Deskripsi | Auth |
|:-------|:---------|:----------|:-----|
| `POST` | `/classification/predict` | Klasifikasi jenis surat (Hybrid: local/gemini) | ✅ |

---

### 👁️ OCR Service (`/ocr`)

| Method | Endpoint | Deskripsi | Auth |
|:-------|:---------|:----------|:-----|
| `POST` | `/ocr/extract-text` | Ekstraksi teks dari gambar (`multipart/form-data`) | ✅ |

---

### 🏷️ NER Service (`/ner`)

| Method | Endpoint | Deskripsi | Auth |
|:-------|:---------|:----------|:-----|
| `POST` | `/ner/extract` | Ekstraksi entitas (nama, lokasi, organisasi) | ✅ |
| `GET` | `/ner/health` | Health check NER service | ❌ |

---

### 🤖 AI Jarvis Service (`/ai`)

| Method | Endpoint | Deskripsi | Auth |
|:-------|:---------|:----------|:-----|
| `POST` | `/ai/summarize` | Ringkasan dokumen otomatis | ✅ |
| `POST` | `/ai/chat` | Chatbot kontekstual (satu dokumen) | ✅ |
| `POST` | `/ai/chat-global` | Chatbot organisasi (semua dokumen + citasi) | ✅ |
| `POST` | `/ai/semantic-search` | Pencarian dokumen berdasarkan makna | ✅ |
| `POST` | `/ai/suggest-disposition` | Saran unit tujuan surat masuk | ✅ |
| `POST` | `/ai/redact-sensitive` | Sensor otomatis data pribadi | ✅ |
| `POST` | `/ai/voice-intent` | Ekstrak niat dari perintah suara | ✅ |
| `POST` | `/ai/extract-tasks` | Ekstrak agenda/tugas dari isi surat | ✅ |
| `POST` | `/ai/generate-reply` | Generate 3 opsi draf balasan surat | ✅ |
| `POST` | `/ai/translate` | Terjemahkan ke Bahasa Indonesia formal | ✅ |
| `POST` | `/ai/analyze-workflow` | Deteksi konflik & saran otomasi workflow | ✅ |
| `POST` | `/ai/extract-budget` | Ekstraksi nilai anggaran & mata uang | ✅ |
| `POST` | `/ai/analyze-priority` | Analisis sentimen, urgensi, dan auto-tagging | ✅ |



---

### 🏗️ Generator Service (`/generator`)

| Method | Endpoint | Deskripsi | Auth |
|:-------|:---------|:----------|:-----|
| `POST` | `/generator/surat-tugas` | Generate HTML Surat Tugas (kop + TTD + nomor) | ✅ |
| `GET` | `/generator/verify/<hash>` | Verifikasi keaslian dokumen (Anti-Fraud) | ❌ |
| `GET` | `/generator/health` | Health check generator | ❌ |

| `GET` | `/generator/health` | Health check generator | ❌ |

---

### 📊 Insight Service (`/insight`)

| Method | Endpoint | Deskripsi | Auth |
|:-------|:---------|:----------|:-----|
| `GET` | `/insight/` | Home insight API | ❌ |
| `GET` | `/insight/api/insights` | Data insight & analitik | ✅ |
| `GET` | `/insight/weekly-summary` | Laporan mingguan AI untuk pimpinan | ✅ |
| `GET` | `/insight/predictive-trends` | Prediksi beban kerja 3 bulan ke depan | ✅ |


---

### ⏰ Reminder Service (`/reminder`)

| Method | Endpoint | Deskripsi | Auth |
|:-------|:---------|:----------|:-----|
| `POST` | `/reminder/` | Buat pengingat/tugas baru | ✅ |
| `GET` | `/reminder/` | List semua pengingat organisasi | ✅ |
| `DELETE` | `/reminder/<id>` | Hapus pengingat | ✅ |
| `GET` | `/reminder/health` | Health check reminder | ❌ |

---

### 🔔 Notification Service (`/notification`)

| Method | Endpoint | Deskripsi | Auth |
|:-------|:---------|:----------|:-----|
| `GET` | `/notification/` | List notifikasi user | ✅ |
| `POST` | `/notification/read/<id>` | Tandai notifikasi sudah dibaca | ✅ |
| `GET` | `/notification/unread-count` | Hitung jumlah notifikasi belum dibaca | ✅ |
| `GET` | `/notification/health` | Health check notification | ❌ |


> 💡 **Tip:** Untuk dokumentasi interaktif lengkap beserta request/response schema, buka **Swagger UI** di `http://localhost:5009/apidocs` saat server berjalan.

---

## 🧪 Contoh Penggunaan API

### Login

```bash
curl -X POST http://localhost:5009/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "Password123"}'
```

### Upload & Proses Dokumen (Full Pipeline)

```bash
curl -X POST http://localhost:5009/document/upload \
  -H "Authorization: Bearer <token>" \
  -F "file=@surat_undangan.png"
```

### Klasifikasi Surat

```bash
curl -X POST http://localhost:5009/classification/predict \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"text": "Dengan hormat, kami mengundang Bapak/Ibu untuk menghadiri rapat..."}'
```

### NER (Ekstraksi Entitas)

```bash
curl -X POST http://localhost:5009/ner/extract \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"text": "Bima Arya dari Universitas Amikom Purwokerto akan menghadiri seminar di Jakarta."}'
```

### AI Summarize

```bash
curl -X POST http://localhost:5009/ai/summarize \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"text": "Isi dokumen surat yang panjang..."}'
```

### Semantic Search

```bash
curl -X POST http://localhost:5009/ai/semantic-search \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"query": "surat tentang anggaran belanja"}'
```

### Generate Surat Tugas

```bash
curl -X POST http://localhost:5009/generator/surat-tugas \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "doc_number": "001/ST/DINAS-PU/2026",
    "task_description": "Melaksanakan koordinasi lapangan terkait proyek jalan.",
    "signatory_name": "Ir. Budi Santoso",
    "city": "Purwokerto"
  }'
```

---

## 🗄️ Skema Database (MongoDB)

| Collection | Deskripsi | Field Utama |
|:-----------|:----------|:------------|
| `users` | Data pengguna | `username`, `email`, `password`, `role`, `org_id`, `delegation_id` |
| `organizations` | Data organisasi | `name`, `created_at` |
| `documents` | Dokumen tersimpan | `doc_id`, `filename`, `content`, `classification`, `entities`, `org_id` |
| `delegations` | Unit/Dinas | `name`, `org_id`, `created_at` |
| `assets` | Kop & TTD Digital | `type` (`letterhead`/`signature`), `delegation_id`, `image_data` |
| `reminders` | Pengingat/agenda | `task`, `date`, `time`, `location`, `org_id`, `is_completed` |
| `invitations` | Undangan member | `email`, `org_id`, `status` (`pending`/`accepted`), `role` |
| `logs` | Audit trail | `service`, `message`, `user_id`, `org_id`, `action`, `timestamp` |
| `notifications` | Notifikasi user | `user_id`, `title`, `message`, `is_read`, `created_at` |
| `otps` | Kode Verifikasi | `email`, `otp`, `expiry`, `created_at` |


---

## 🔒 Keamanan & Privasi

- **JWT Authentication** — Setiap request dilindungi token JWT dengan expiry. Token dikirim via header `Authorization: Bearer <token>`.
- **Role-Based Access Control (RBAC)** — Decorator `@role_required('owner')` membatasi akses fitur sensitif (delegasi, aset, delete) hanya untuk pemilik organisasi.
- **Data Isolation** — Setiap query di-filter berdasarkan `org_id` untuk memastikan data antar organisasi tidak bocor.
- **Smart Redaction** — Endpoint `/ai/redact-sensitive` secara otomatis menyensor NIK, No. HP, dan alamat sebelum dokumen dibagikan.
- **Audit Logging** — Seluruh aksi penting (login, upload, delete, mutasi, generate) dicatat di collection `logs` untuk transparansi dan audit trail.

---

## 📝 Catatan Pengembangan

- **Logging Terpusat** — Seluruh service menggunakan fungsi `log_event()` dari `common/logger.py` untuk konsistensi pencatatan.
- **Konfigurasi Terpusat** — Semua environment variable dikelola melalui `common/config.py` menggunakan `python-dotenv`.
- **Model ML Lokal** — File model `.safetensors` di folder `models/` berukuran besar dan tidak di-push ke GitHub. Salin file model secara manual setelah clone.
- **IndoBERT NER** — Model `cahya/bert-base-indonesian-NER` diunduh otomatis dari HuggingFace Hub saat pertama kali dijalankan.
- **OCR via Gemini** — OCR menggunakan Google Gemini API (multimodal vision) untuk akurasi tinggi dan performa yang stabil.
- **Template HTML** — Generator Surat Tugas menggunakan Jinja2 `render_template_string` untuk fleksibilitas penuh. Output HTML dapat dikonversi ke PDF di sisi frontend.

---

## 👥 Tim Pengembang

Proyek ini dikembangkan oleh **Bima Arya Satya** dan **Geraldi Novalino Putra** sebagai bagian dari **Capstone Project Semester 6** — Universitas Harkat Negeri.

---

<p align="center">
  <sub>Built with ❤️ using Flask, MongoDB, Mistral AI, Google Gemini, and IndoBERT</sub>
</p>
