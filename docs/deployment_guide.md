# Step-by-Step Production Deployment Guide

This guide walks you through deploying your **AI Personal Assistant** to production using:
- **Frontend**: [Vercel](https://vercel.com) (Next.js)
- **Backend**: [Render](https://render.com) (FastAPI Python)
- **Database**: [Supabase](https://supabase.com) or [Neon](https://neon.tech) (PostgreSQL)

---

## Step 1 — Create a Free PostgreSQL Database

### Using Supabase:
1. Sign up at [supabase.com](https://supabase.com).
2. Click **New Project** and name it `ai-personal-assistant`.
3. Set a secure Database Password.
4. Once created, go to **Project Settings** -> **Database**.
5. Copy the **URI Connection String** under *Connection String* -> *URI*:
   ```text
   postgresql://postgres:[YOUR-PASSWORD]@db.xxxxxx.supabase.co:5432/postgres
   ```

### Using Neon.tech:
1. Sign up at [neon.tech](https://neon.tech).
2. Create a project named `ai-personal-assistant`.
3. Copy the pooled PostgreSQL connection string:
   ```text
   postgresql://alex:password@ep-cool-site-123456.us-east-2.aws.neon.tech/neondb?sslmode=require
   ```

---

## Step 2 — Deploy Backend to Render

1. Push your latest code to your **GitHub repository**.
2. Log into [Render](https://dashboard.render.com).
3. Click **New +** -> **Web Service**.
4. Connect your GitHub repository.
5. Configure the service settings:
   - **Name**: `ai-assistant-backend`
   - **Root Directory**: `backend`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
6. Under **Environment Variables**, add:
   - `DATABASE_URL`: `<Your Supabase/Neon Postgres URL from Step 1>`
   - `GOOGLE_CLIENT_ID`: `<Your Google OAuth Client ID>`
   - `GOOGLE_CLIENT_SECRET`: `<Your Google OAuth Client Secret>`
   - `OAUTH_REDIRECT_URI`: `https://ai-assistant-backend.onrender.com/auth/callback` *(replace with your actual Render URL)*
   - `FRONTEND_ORIGIN`: `https://ai-personal-assistant.vercel.app` *(replace with your actual Vercel URL)*
   - `SESSION_SECRET`: `<Generate a random 32-character secret string>`
   - `GROQ_API_KEY`: `<Your Groq API key>`
   - `SARVAM_API_KEY`: `<Your Sarvam API key>`
   - `ALLOWED_USER_EMAILS`: `["patelnakul36@gmail.com"]` *(locks app to your Google email only)*
7. Click **Create Web Service**.
8. Note down your backend live URL (e.g. `https://ai-assistant-backend.onrender.com`).

---

## Step 3 — Update Google OAuth Authorized URIs

1. Go to [Google Cloud Console Credentials](https://console.cloud.google.com/apis/credentials).
2. Click your OAuth 2.0 Client ID.
3. Under **Authorized JavaScript Origins**, add:
   - `https://ai-personal-assistant.vercel.app` (your Vercel frontend domain)
4. Under **Authorized redirect URIs**, add:
   - `https://ai-assistant-backend.onrender.com/auth/callback` (your Render backend callback URL)
5. Click **Save**.

---

## Step 4 — Deploy Frontend to Vercel

1. Log into [Vercel](https://vercel.com).
2. Click **Add New** -> **Project**.
3. Import your GitHub repository.
4. Set **Root Directory** to `frontend`.
5. Under **Environment Variables**, add:
   - `NEXT_PUBLIC_BACKEND_URL`: `https://ai-assistant-backend.onrender.com` *(your Render backend URL)*
6. Click **Deploy**.

---

## Step 5 — Verification & Testing

1. Open your Vercel URL in a browser (`https://ai-personal-assistant.vercel.app`).
2. Click **Connect Google Account**.
3. Authenticate with `patelnakul36@gmail.com`.
4. Verify you land back on the assistant dashboard authenticated.
5. Try sending a text message ("What are my tasks today?") and a voice command!
6. Verify actions and logs are stored persistently in your cloud PostgreSQL database.
