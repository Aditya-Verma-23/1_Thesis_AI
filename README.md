# Thesis AI — Intelligent Research Assistant

Thesis AI is a comprehensive full-stack application designed to accelerate the academic research process. It allows users to ask complex research questions, search for relevant academic papers and web sources using advanced filters, and synthesizes the findings into a cohesive, readable document with citations.

## 🚀 Features

* **Advanced Search Filters**: Filter research by citations, journal quality, publication types (journals, preprints, conferences), and sources (Semantic Scholar, OpenAlex, PubMed, arXiv, etc.).
* **Real-Time Data Streaming**: Leverages Server-Sent Events (SSE) to stream live search progress and token-by-token generation of the synthesized research paper directly to the frontend.
* **Paper Synthesis**: Automatically reads and synthesizes information from top search results to produce a consolidated, easy-to-read summary of the literature.
* **Session Management & Export**: Automatically stores query sessions in the backend and allows users to download the synthesized research paper as a `.txt` file.
* **Modern UI**: Built with React, featuring a clean, responsive layout, animated components, and a toggleable filter panel.

---

## 🛠️ Tech Stack

### Frontend
* **Framework**: React 18 + Vite
* **Styling**: Vanilla CSS (`index.css`)
* **Markdown Rendering**: `react-markdown` with `rehype-raw`
* **Port**: Runs on `http://localhost:3333`

### Backend
* **Framework**: FastAPI (Python)
* **Async Processing**: Python `asyncio` for non-blocking search and synthesis operations.
* **Libraries**: `loguru` for logging, `pydantic` for data models.
* **Port**: Runs on `http://localhost:8888` (Configured via `uvicorn`)

---

## 🏗️ Project Architecture & Data Flow

The application follows a standard client-server architecture with real-time streaming capabilities:

1. **User Input (Frontend)**: The user enters a research query and configures filters (e.g., minimum citations, target databases) in the UI.
2. **API Request**: The React frontend sends a `POST` request to the backend `/api/query` endpoint with the query string and selected filters.
3. **Searching (Backend - `search.py`)**: The backend searches configured academic databases (Semantic Scholar, OpenAlex, etc.) asynchronously. It yields an SSE update to the frontend indicating the "Searching" stage.
4. **Results Streaming**: Once papers are found, the backend streams the top results (`SearchResult` models) back to the frontend to display immediately.
5. **Synthesis (Backend - `synthesizer.py`)**: The backend uses the content/abstracts of the retrieved papers and begins generating a synthesized response.
6. **Token Streaming (SSE)**: As the synthesized paper is generated, the backend streams it token-by-token back to the frontend, which dynamically updates the UI via `react-markdown`.
7. **Session Storage**: Once synthesis is complete, the backend stores the session context (`session_store.py`) in memory or a local cache.
8. **Export**: The user can click a download button on the frontend, triggering a `GET` request to `/api/download/{session_id}` to retrieve the full synthesized text.

---

## ⚙️ Installation & Setup

### Prerequisites
* Node.js (v18+ recommended)
* Python (3.9+ recommended)

### 1. Backend Setup

1. Open a terminal and navigate to the `backend` directory:
   ```bash
   cd backend
   ```
2. Create and activate a virtual environment (optional but recommended):
   ```bash
   python -m venv .venv
   # Windows
   .venv\Scripts\activate
   # Mac/Linux
   source .venv/bin/activate
   ```
3. Install the required Python packages:
   ```bash
   pip install -r requirements.txt
   ```
4. Start the FastAPI backend server:
   ```bash
   uvicorn main:app --port 8888 --reload
   ```
   The backend API will be available at `http://localhost:8888`.

### 2. Frontend Setup

1. Open a separate terminal and navigate to the `frontend` directory:
   ```bash
   cd frontend
   ```
2. Install the Node modules:
   ```bash
   npm install
   ```
3. Start the Vite development server:
   ```bash
   npm run dev
   ```
   The frontend application will be available at `http://localhost:3333`.

---

## 📂 Key Files Overview

* **`frontend/src/App.jsx`**: Main React component managing state, SSE event listeners, and UI layout.
* **`frontend/src/components/FilterPanel.jsx`**: Sidebar component for advanced search filtering.
* **`frontend/vite.config.js`**: Vite configuration containing the proxy setup to route `/api` calls to the FastAPI backend.
* **`backend/main.py`**: The FastAPI application entry point defining the SSE stream (`/api/query`) and download endpoints.
* **`backend/search.py`**: Contains the logic for fetching research papers from various APIs.
* **`backend/synthesizer.py`**: Handles the logic for aggregating research data and generating the final synthesized response.
* **`backend/session_store.py`**: Manages temporary storage of generated results for downloading.

