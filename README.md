# Thesis AI

AI-powered research assistant that searches DuckDuckGo + Google for thesis/research papers
and generates a downloadable synthesis paper.

## Ports
- **Frontend**: http://localhost:3333
- **Backend**: http://localhost:8888

## Setup & Run

### 1. Backend (Python)
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate       # Windows
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8888 --reload
```

### 2. Frontend (React)
```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3333

## Features
- 💬 Chat UI — type any research question
- 🔎 Searches DuckDuckGo + Google concurrently
- 📄 Shows top 10 research/thesis paper results
- 📝 AI generates a full synthesis paper (uses Ollama locally)
- ⬇️ Download the synthesis paper as a `.txt` file
- 🕑 Recent search history in sidebar
- ✅ Backend health check with visual overlay

## Ollama (optional, for synthesis)
If you have Ollama installed:
```bash
ollama pull qwen2.5:14b-instruct
```
If Ollama is not running, the app falls back to a template-based paper automatically.
