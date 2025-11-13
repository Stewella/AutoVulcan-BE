# 🧭 SEIGE Runner — API Contract (Backend ↔ Frontend)

**Version:** 1.0  
**Base URL (dev):** `http://31.97.109.218:8000`  
**Prefix:** `/api/v1`  
**Auth:** JWT Bearer (Authorization header or HttpOnly cookie)

---

## 🌿 Overview

API ini menjadi jembatan antara **frontend SEIGE Runner Dashboard** dengan **backend (FastAPI)** dan **core engine (Java)**.  
Tujuan utamanya: menjalankan analisis otomatis terhadap project Java, memantau status eksekusi, dan mengambil hasil deteksi CVE.

---

## 📋 Endpoint Summary

| No | Method | Endpoint | Auth | Description |
|----|:------:|-----------|:----:|-------------|
| 1 | GET | `/health` | ❌ | Server health check |
| 2 | POST | `/api/v1/auth/register` | ❌ | Register user |
| 3 | POST | `/api/v1/auth/token` | ❌ | Login user (return JWT) |
| 4 | POST | `/api/v1/analysis/run` | ✅ | Start SEIGE analysis pipeline |
| 5 | GET | `/api/v1/analysis/status/{execution_id}` | ✅ | Get pipeline status + logs |
| 6 | GET | `/api/v1/analysis/result/{execution_id}` | ✅ | Get final analysis result |
| 7 | GET | `/api/v1/analysis/export/{execution_id}?format={json|pdf}` | ✅ | Export result (JSON/PDF) |
| 8 | POST | `/api/v1/core/run` | ✅ | Proxy request ke core-engine |
| 9 | POST | `/api/v1/analysis/reset` | ✅ | Reset pipeline (dev only) |

---

## 🔑 Authentication

### Login (GET JWT)
**Endpoint:** `POST /api/v1/auth/token`

**Request**
```json
{
  "username": "dev",
  "password": "devpass"
}
