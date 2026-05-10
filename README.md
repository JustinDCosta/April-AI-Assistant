# April AI: The Hybrid Dual-Brain Voice Assistant

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

April is an experimental, highly-optimized AI voice assistant designed to bridge the gap between local hardware privacy and cloud-based reasoning speed. By utilizing a custom "Dual-Brain Waterfall Architecture," April routes your voice commands silently through your local GPU, and only reaches out to the cloud when she needs serious brainpower. 

The result? Near-zero latency, total desktop automation, and an AI that actually remembers what you said 5 minutes ago.

## The Architecture

April doesn't just use one AI model; she uses a self-healing waterfall of three different models:

1. **The Router (Local Qwen 2.5 3B):** Running 100% offline via Ollama. It silently intercepts your voice commands and decides if you want to perform a physical computer action (like opening an app or searching the web). This completely bypasses API limits for basic tasks.
2. **The Genius (Cloud Llama 3.3 70B):** Powered by Groq's LPUs. If you ask a complex question or need a web search summarized, Qwen passes the data here. It responds at over 800 words per second.
3. **The Speedster (Cloud Llama 3.1 8B):** If you ever hit a rate limit on the 70B model, the system instantly catches the error and falls back to this high-volume model without you even noticing. 
4. **The Survivor:** If your Wi-Fi dies completely, April falls back to your local Qwen model to keep the conversation going offline.

## Features

* **Live Web Searching:** Uses DuckDuckGo (`ddgs`) to scrape real-time news and answer questions about current events.
* **Desktop Automation:** Can open applications, adjust system volume, put the PC to sleep, and set timers.
* **Smart Memory:** Automatically saves important facts about you to a local `memory.json` file and injects recent chat history into her context window so she never loses the thread of conversation.
* **Bulletproof Shutdown:** Features an "air-gapped" shutdown protocol. She cannot accidentally turn off your PC—you must speak a highly specific, hardcoded passphrase.
* **Auto-Logging:** Silently builds a beautiful `chat_history.md` file of all your conversations.

## Repository Structure

* `april.py`: The main execution loop. Handles the microphone, wake-word detection, "Ghost Word" filtering, and the air-gapped shutdown safety logic.
* `brain.py`: The Waterfall Routing Engine. Handles the logic between Ollama and Groq, as well as short-term memory management.
* `tools.py`: The physical toolbelt containing the Python scripts for web scraping, weather fetching, volume control, and note-taking.
* `.env.example`: A template for your API keys.

*(Note: User data like `memory.json`, `chat_history.md`, and `.env` are explicitly ignored by Git to protect your privacy).*

## Installation & Setup

Because April relies on local voice models and local LLMs, setup requires a few steps to get your environment ready.

### 1. Prerequisites
* **Python 3.10+**
* **Ollama:** Download and install [Ollama](https://ollama.com/) to run local models.
* **Groq API Key:** Get a free API key from the [Groq Console](https://console.groq.com/).

### 2. Clone the Repository
```bash
git clone [https://github.com/YourUsername/April-AI-Assistant.git](https://github.com/YourUsername/April-AI-Assistant.git)
cd April-AI-Assistant
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Download Local Models
You will need to pull the local routing model into Ollama. Open your terminal and run:
```bash
ollama pull qwen2.5:3b
```

**Voice Models (Action Required):** To keep this repository lightweight, the large audio models are not included. You must manually download the Whisper STT and Piper TTS models:
1. Create a folder named `whisper_model/` and place your `.bin` model inside.
2. Create a folder named `piper_tts/` and place your `.onnx` voice model inside. 
*(Check the script comments in `audio.py` or `april.py` for the exact model links if you are missing them).*

### 5. Configure Your Keys
1. Rename the `.env.example` file to `.env`.
2. Open it and paste your Groq API key:
```env
GROQ_API_KEY=gsk_your_api_key_here
```

## Running April

Once everything is installed, simply run:
```bash
python april.py
```
Wait for her to say *"All systems are online,"* and then try saying:
> *"April, search the internet for the latest news on artificial intelligence."*

**Emergency Shutdown:** To safely power off your physical computer, say exactly: *"April shut down the computer please."*

## License

This project is licensed under the **MIT License** - see the [LICENSE](LICENSE) file for details. Feel free to fork, modify, and build your own April!