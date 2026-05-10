# April

**April** is a hybrid, dual-brain voice assistant: a **local** small language model routes *when* to call tools, while a **cloud** Groq model (Llama 3.3 70B) delivers fast conversational replies—with a **waterfall** of fallbacks if the cloud tier is unavailable.

---

## Hybrid dual-brain architecture

| Layer | Role |
|--------|------|
| **Local router (Ollama / Qwen 2.5 3B)** | Decides whether the user wants a *physical* or *information* action (web search, YouTube, weather, volume, notes, etc.) versus normal chat. |
| **Cloud responder (Groq / Llama 3.3 70B)** | Generates natural, concise spoken answers and uses web context when search was invoked. |
| **Waterfall fallback** | If the 70B call fails → **Llama 3.1 8B Instant** on Groq; if Groq is fully unreachable → **local Qwen** completes the reply. |

Tool results (e.g. weather strings, non-search actions) can be returned immediately without hitting the cloud; **web search** feeds snippets into Groq so answers stay grounded.

---

## How the modules fit together

### `april.py` — loop, safety, and logging

- Listens via `audio.listen()`, applies **wake words** and **conversation mode** phrases, and strips commands.
- Enforces **hard safety paths** (e.g. exact shutdown phrase, exiting the loop without OS shutdown).
- Calls `brain.process_intent()` for each command and **`speak()`** for the reply.
- Appends exchanges to `chat_history.md` (personal log; keep out of version control—see `.gitignore`).

### `brain.py` — waterfall routing and memory

- Loads long-term lines from `memory.json` into the system prompt.
- **Phase 1:** `ollama.chat(..., model='qwen2.5:3b', tools=OLLAMA_TOOLS)` — tool routing only.
- **Phase 2:** Executes matching functions from `tools.AVAILABLE_TOOLS` (e.g. `search_web` → context string).
- **Phase 3:** Sends chat + optional web context to **Groq** (`llama-3.3-70b-versatile`), then **8B instant**, then **local Qwen** as last resort.
- Maintains short-term `chat_history` (last N turns).

### `tools.py` — actions

- Implements **DuckDuckGo** search (`ddgs`), **YouTube** open-first-result, **Open-Meteo** weather (via IP geolocation), **volume** (`pycaw` + **PyAutoGUI** media keys), **timers**, **notes** (`notes.md`), **sleep**, app launch macros, etc.
- **`APP_DIRECTORY`** / **`PROJECT_DIRECTORY`** are **machine-specific**—forks should edit these maps for their own paths (not secrets, but not portable).

---

## Features

- **Dynamic tool use** driven by the local router: weather, YouTube playback, DuckDuckGo web search, Windows volume and media keys, timed alarms, and markdown notes.
- **Waterfall LLM stack** for resilience: 70B → 8B → local Qwen.
- **Voice pipeline**: Faster Whisper (GPU-capable) for STT; Piper for TTS (see `audio.py` and local `piper_tts` assets).
- **Long-term memory** in `memory.json` (gitignored by default).

---

## Prerequisites

- **Windows** (current scripts use Win32 APIs, `winsound`, and Windows shutdown/sleep commands).
- **[Ollama](https://ollama.com/)** with **`qwen2.5:3b`** pulled.
- **[Groq](https://console.groq.com/)** API key (free tier available).
- **Python 3.10+** recommended.
- **Microphone** and (for GPU Whisper) a suitable **NVIDIA** setup if you use CUDA in `audio.py`.

---

## Installation and setup

### 1. Install Ollama and the router model

Install Ollama from the official site, then:

```bash
ollama pull qwen2.5:3b
```

Ensure the Ollama service is running so `ollama` Python calls succeed.

### 2. Clone and create a virtual environment

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

On Windows, **PyAudio** may need a [matching wheel](https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio) if `pip install` fails.

### 3. Configure environment variables

```bash
copy .env.example .env
```

Edit `.env` and set:

```env
GROQ_API_KEY=your_actual_key_here
```

Never commit `.env`. Only `.env.example` belongs on GitHub.

### 4. Local assets (voice)

- **Faster Whisper**: `audio.py` expects a local model directory `./whisper_model` (and optional CUDA DLL paths via your venv).
- **Piper**: place `piper.exe` / `piper`, voice `.onnx`, and related files under `piper_tts/` as referenced in `audio.py`.

### 5. Customize tool paths (optional)

Edit `tools.py` — update **`APP_DIRECTORY`** and **`PROJECT_DIRECTORY`** for your PC.

### 6. Run April

```bash
python april.py
```

---

## Security notes

- **If an API key was ever committed to git or shared, revoke it** in the [Groq console](https://console.groq.com/) and create a new key.
- Keep **`.env`**, **`memory.json`**, **`chat_history.md`**, and **`notes.md`** out of public repos (see `.gitignore`).

---

## Repository layout (core)

| File | Purpose |
|------|---------|
| `april.py` | Main loop, wake/conversation modes, logging |
| `brain.py` | Router + Groq waterfall + chat memory |
| `tools.py` | Tool implementations and app maps |
| `audio.py` | Listen (Whisper) / speak (Piper) |

---

## Third-party services

- **Groq** — cloud chat completions.
- **Ollama** — local **qwen2.5:3b** routing and fallback.
- **DuckDuckGo** (via **`ddgs`**) — web search.
- **Open-Meteo** & **geojs.io** — weather and coarse location (see `tools.py`).

---
