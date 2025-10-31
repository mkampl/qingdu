# QingDu Setup Guide

## Quick Start with Docker 🐳

```bash
# 1. Copy environment file
cp .env.example .env

# 2. Start the application
docker-compose up -d

# 3. Access the application
# Open http://localhost:8000
```

That's it! The default `.env.example` contains a development SECRET_KEY.

**⚠️ IMPORTANT for Production:**
Generate a new SECRET_KEY before deploying:
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```
Update the `SECRET_KEY` in your `.env` file with the generated key.

---

## Alternative: Quick Setup Script

```bash
./setup.sh
docker-compose up -d
```

---

## Manual Setup (Without Docker)

1. **Create environment file:**
   ```bash
   cp .env.example .env
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Start the application:**
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```

---

## Environment Variables

### Required
- `SECRET_KEY` - JWT signing key (generate with secrets.token_urlsafe(32))

### Optional
- `DEEPL_API_KEY` - DeepL translation API key
- `GOOGLE_TRANSLATE_API_KEY` - Google Translate API key
- `PORT` - Server port (default: 8000)
- `LOG_LEVEL` - Logging level (default: INFO)
- `ALLOWED_ORIGINS` - CORS allowed origins (default: *)

---

## Default Credentials

After starting the application, login with:
- **Username:** `admin`
- **Password:** `admin123`

⚠️ You will be prompted to change the password on first login.

---

## Troubleshooting

### "SECRET_KEY must be set" Error
Make sure you have copied `.env.example` to `.env`:
```bash
cp .env.example .env
```

### Docker Container Won't Start
Check logs:
```bash
docker-compose logs web
```

### Port Already in Use
Change the port in `.env`:
```env
PORT=8001
```

---

## New in This Version

✅ **Security Improvements:**
- Mandatory SECRET_KEY validation
- Login rate limiting (5 attempts/minute)

✅ **Performance:**
- TTL caches with size limits
- Automatic retry for network errors

✅ **Debugging:**
- Structured logging with configurable levels
- Request ID tracking (X-Request-ID header)

✅ **Configuration:**
- Centralized constants
- Environment validation at startup
- CORS configuration

See commit history for detailed changes.
