"""Side-effect tools invoked by the local router (Ollama).

Maps spoken intents to OS actions: applications, media keys, volume, timers, notes,
web search, and weather. Paths in ``APP_DIRECTORY`` and ``PROJECT_DIRECTORY`` are
host-specific and must be edited per deployment.
"""

from typing import Callable, Any
from io import BytesIO
from groq import Groq
from pycaw.pycaw import AudioUtilities
from ddgs import DDGS
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from pypdf import PdfReader
from shazamio import Shazam

import webbrowser
import subprocess
import urllib.request
import urllib.parse
import re
import os
import json
import time
import winsound
import pyautogui
import datetime
import pyperclip
import psutil
import base64
import os.path
import uuid
import threading
import chromadb
import asyncio
import sounddevice as sd
import soundfile as sf

# Initialize Local Vector Database
chroma_client: Any = chromadb.PersistentClient(path="./chroma_db")
knowledge_collection: Any = chroma_client.get_or_create_collection(name="april_knowledge")

APP_DIRECTORY: dict[str, str] = {
    "cyberpunk": r"C:\Program Files (x86)\Steam\steamapps\common\Cyberpunk 2077\bin\x64\Cyberpunk2077.exe",
    "valorant": r"C:\Riot Games\Riot Client\RiotClientServices.exe",
    "discord": r"C:\Users\aldre\AppData\Local\Discord\Update.exe --processStart Discord.exe",
    "notepad": "notepad.exe",
    "word": "winword.exe",
    "excel": "excel.exe",
    "chrome": "chrome.exe",
    "spotify": "spotify.exe",
    "vs code": r"C:\Users\aldre\AppData\Local\Programs\Microsoft VS Code\Code.exe",
    "vscode": r"C:\Users\aldre\AppData\Local\Programs\Microsoft VS Code\Code.exe",
    "VSCode": r"C:\Users\aldre\AppData\Local\Programs\Microsoft VS Code\Code.exe",
    "VS Code": r"C:\Users\aldre\AppData\Local\Programs\Microsoft VS Code\Code.exe",
    "visual studio code": r"C:\Users\aldre\AppData\Local\Programs\Microsoft VS Code\Code.exe"
}

PROJECT_DIRECTORY: dict[str, str] = {
    "april": r"C:\Users\aldre\Documents\DRIVE\Projects\APRIL_AI_V1",
    "website": r"C:\Users\aldre\Documents\DRIVE\Projects\MyWebsite"
}


def play_youtube_video(query: str) -> str:
    """Open the first YouTube search result for ``query`` in the default browser.

    Scrapes the results page HTML for a watch URL; no official API key required.

    Args:
        query: Search terms for YouTube.

    Returns:
        User-facing status message.
    """
    print(f"[SYSTEM] Finding video for: {query}")
    try:
        search_url = "https://www.youtube.com/results?search_query=" + query.replace(' ', '+')
        html = urllib.request.urlopen(search_url)

        video_ids = re.findall(r"watch\?v=(\S{11})", html.read().decode())
        if video_ids:
            video_url = "https://www.youtube.com/watch?v=" + video_ids[0]
            print(f"[SYSTEM] Playing: {video_url}")
            webbrowser.open(video_url)
            return f"I'm playing {query} on YouTube right now."
        return "I couldn't find a video for that."
    except Exception as e:
        return f"Failed to play video. Error: {e}"


def open_application(app_name: str) -> str:
    """Launch an executable by mapped key or resolve a short name via the Windows shell.

    STT output often includes punctuation; stripping it avoids silent misses in
    ``APP_DIRECTORY``. Full paths use ``subprocess.Popen``; bare names use ``start``
    so ``PATH`` resolution matches manual typing.

    Args:
        app_name: Raw application name from the assistant pipeline.

    Returns:
        User-facing status message.
    """
    app_key = app_name.lower().replace(".exe", "")

    for char in [".", ",", "!", "?", "'", '"']:
        app_key = app_key.replace(char, "")

    app_key = app_key.strip()

    print(f"[SYSTEM] Cleaned App Key: '{app_key}'")

    try:
        target = APP_DIRECTORY.get(app_key, app_key)

        if ":" in target or "\\" in target:
            subprocess.Popen(target)
        else:
            os.system(f'start "" "{target}"')

        return f"I've opened {app_key} for you."

    except Exception as e:
        return f"I had trouble opening {app_key}. You might need to add the exact path to my dictionary."


def manage_git(project_name: str) -> str:
    """Run ``git add``, ``commit``, and ``push`` in a configured project directory.

    Imports ``audio`` inside the function to avoid an import cycle with ``brain``.

    Args:
        project_name: Key into ``PROJECT_DIRECTORY``.

    Returns:
        User-facing status message.
    """
    from audio import speak, listen

    proj_key = project_name.lower()
    path = PROJECT_DIRECTORY.get(proj_key)

    if not path:
        return f"I don't have the folder path for the {project_name} project configured yet."

    speak(f"Preparing to push the {project_name} project. What should the commit message be?")
    commit_message = listen()

    if not commit_message:
        return "I didn't hear a commit message, so I canceled the git push."

    try:
        print(f"[SYSTEM] Running Git commands in {path}")
        subprocess.run(["git", "add", "."], cwd=path, check=True)
        subprocess.run(["git", "commit", "-m", commit_message], cwd=path, check=True)
        subprocess.run(["git", "push"], cwd=path, check=True)
        return "Your code has been successfully committed and pushed to the repository."
    except subprocess.CalledProcessError:
        return "There was an error running the git commands. You might want to check your terminal."


def shutdown_computer() -> str:
    """Force immediate Windows shutdown.

    Returns:
        User-facing status message.
    """
    print("[SYSTEM] Initiating force shutdown...")
    os.system("shutdown /s /f /t 0")
    return "Shutting down all core systems now. Goodbye."


def sleep_computer() -> str:
    """Suspend the workstation using the stock Windows power helper.

    Returns:
        User-facing status message.
    """
    print("[SYSTEM] Initiating sleep mode...")
    os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
    return "Going to sleep. Wake me if you need me."


def check_local_weather(city: str = "Sevran", **kwargs: Any) -> str:
    """Fetches current weather for a specified city using Open-Meteo Geocoding."""

    # Catch empty strings or None values passed by the LLM
    if not city or not str(city).strip():
        city = "Sevran"

    print(f"[SYSTEM] Fetching weather for {city}...")
    try:
        headers: dict[str, str] = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json'
        }

        # 1. Geocode the city name to get exact latitude and longitude
        safe_city: str = urllib.parse.quote(city)
        geo_url: str = f"https://geocoding-api.open-meteo.com/v1/search?name={safe_city}&count=1&language=en&format=json"

        geo_req: Any = urllib.request.Request(geo_url, headers=headers)
        with urllib.request.urlopen(geo_req) as response:
            geo_data: dict[str, Any] = json.loads(response.read().decode())

        if not geo_data.get("results"):
            return f"I couldn't find the GPS coordinates for {city}."

        lat: float = geo_data["results"][0]["latitude"]
        lon: float = geo_data["results"][0]["longitude"]
        resolved_city: str = geo_data["results"][0]["name"]

        # 2. Fetch the weather using those exact coordinates
        weather_url: str = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
        weather_req: Any = urllib.request.Request(weather_url, headers=headers)

        with urllib.request.urlopen(weather_req) as response:
            weather_data: dict[str, Any] = json.loads(response.read().decode())

        current: dict[str, Any] = weather_data.get("current_weather", {})
        temp_c: float = current.get("temperature", 0.0)
        temp_f: float = round((temp_c * 9 / 5) + 32, 1)

        weather_code: int = current.get("weathercode", 0)
        conditions: dict[int, str] = {
            0: "clear skies", 1: "mostly clear", 2: "partly cloudy", 3: "overcast",
            45: "foggy", 48: "foggy", 51: "light drizzle", 53: "moderate drizzle",
            55: "heavy drizzle", 61: "slight rain", 63: "moderate rain", 65: "heavy rain",
            71: "slight snow", 73: "moderate snow", 75: "heavy snow", 95: "thunderstorms"
        }
        condition_text: str = conditions.get(weather_code, "mixed conditions")

        return f"Currently in {resolved_city}, it is {temp_c} degrees Celsius, or {temp_f} Fahrenheit, with {condition_text}."

    except Exception as e:
        print(f"[Weather Error]: {e}")
        return "I'm having trouble connecting to the weather satellites right now."


def save_memory(fact: str) -> str:
    """Append ``fact`` to ``memory.json`` as a JSON array of strings.

    Args:
        fact: Sentence to persist for future system prompts.

    Returns:
        User-facing confirmation string.
    """
    memory_file = "memory.json"
    memories = []

    print(f"[SYSTEM] Saving to memory: {fact}")
    if os.path.exists(memory_file):
        with open(memory_file, "r") as f:
            memories = json.load(f)

    memories.append(fact)

    with open(memory_file, "w") as f:
        json.dump(memories, f)

    return f"I will remember that {fact}."


def media_control(action: str) -> str:
    """Send multimedia keyboard shortcuts via PyAutoGUI.

    Volume step counts are coarse (not calibrated to OS percentage).

    Args:
        action: One of the router-defined media actions.

    Returns:
        Fixed acknowledgment string.
    """
    print(f"[SYSTEM] Executing media control: {action}")

    if action == "play_pause":
        pyautogui.press("playpause")
    elif action == "next":
        pyautogui.press("nexttrack")
    elif action == "previous":
        pyautogui.press("prevtrack")
    elif action == "mute":
        pyautogui.press("volumemute")
    elif action == "volume_up":
        pyautogui.press("volumeup", presses=10)
    elif action == "volume_down":
        pyautogui.press("volumedown", presses=10)

    return "Done."


# Global registry to track active timers
active_timers: dict[str, threading.Event] = {}


def timer_thread(minutes: int, timer_id: str, cancel_event: threading.Event) -> None:
    """Background worker that waits for either the timeout or a cancel signal."""
    # The wait() function acts like sleep, but returns True if the cancel_event is triggered early
    if cancel_event.wait(timeout=minutes * 60):
        print(f"\n[SYSTEM] Timer {timer_id} was successfully cancelled.")
    else:
        print("\n[SYSTEM] TIMER FINISHED!")
        for _ in range(3):
            winsound.Beep(1000, 500)
            time.sleep(0.1)

    # Clean up the registry when done or cancelled
    active_timers.pop(timer_id, None)


def set_timer(minutes: int, **kwargs: Any) -> str:
    """Starts a cancelable daemon timer thread."""
    print(f"[SYSTEM] Starting {minutes} minute background timer...")

    timer_id: str = str(uuid.uuid4())[:8]
    cancel_event: threading.Event = threading.Event()
    active_timers[timer_id] = cancel_event

    t: threading.Thread = threading.Thread(target=timer_thread, args=(minutes, timer_id, cancel_event))
    t.daemon = True
    t.start()

    return f"I have set a timer for {minutes} minutes."


def cancel_all_timers(**kwargs: Any) -> str:
    """Sends the kill signal to all currently running timers."""
    print("[SYSTEM] Cancelling active timers...")

    if not active_timers:
        return "You do not have any active timers running right now."

    count: int = len(active_timers)

    # Trigger the event flag for every running thread
    for cancel_event in active_timers.values():
        cancel_event.set()

    active_timers.clear()
    return f"I have cancelled {count} active timers."


def set_volume(level: int) -> str:
    """Set master playback volume using pycaw endpoint volume API.

    Args:
        level: Target percentage (clamped 0–100).

    Returns:
        User-facing status message.
    """
    print(f"[SYSTEM] Setting system volume to {level}%")
    try:
        device = AudioUtilities.GetSpeakers()

        level = max(0, min(100, level))

        device.EndpointVolume.SetMasterVolumeLevelScalar(level / 100.0, None)

        return f"I've set your volume to {level} percent."
    except Exception as e:
        print(f"[❌ Volume Error]: {e}")
        return "I had trouble adjusting the exact volume."


def take_note(note_text: str) -> str:
    """Append a checklist line to ``notes.md``.

    Args:
        note_text: Raw note body.

    Returns:
        User-facing status message.
    """
    print(f"[SYSTEM] Saving note: {note_text}")
    file_name = "notes.md"

    now = datetime.datetime.now().strftime("%Y-%m-%d %I:%M %p")

    markdown_entry = f"- [ ] **{now}**: {note_text}\n"

    try:
        with open(file_name, "a", encoding="utf-8") as f:
            if os.path.getsize(file_name) == 0:
                f.write("# 📝 April's Notebook\n\n")

            f.write(markdown_entry)

        return "I have noted that down for you."
    except Exception as e:
        print(f"[❌ Note Error]: {e}")
        return "I had trouble writing that down."


def search_web(query: str) -> str:
    """Run a DuckDuckGo text search and concatenate top snippets.

    Args:
        query: Search string.

    Returns:
        Concatenated excerpt block or an error string.
    """
    print(f"[SYSTEM] Searching the web for: {query}")
    try:
        results_text = ""

        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))

            for i, result in enumerate(results):
                title = result.get('title', 'Unknown Source')
                body = result.get('body', '')
                results_text += f"Source {i + 1} ({title}):\n{body}\n\n"

        if not results_text.strip():
            return "I couldn't find anything on the web about that."

        return results_text

    except Exception as e:
        print(f"[❌ Web Search Error]: {e}")
        return "I had trouble connecting to the internet search engine."


def read_clipboard(**kwargs: Any) -> str:
    """Reads the current text on the user's clipboard."""
    print("[SYSTEM] Reading clipboard data...")
    try:
        text: str = pyperclip.paste()
        if not text.strip():
            return "The user's clipboard is currently empty."

        # Limit the clipboard text so it doesn't blow up the API limits
        if len(text) > 3000:
            text = text[:3000] + "... [Text truncated for length]"

        return f"Here is the exact text currently copied to the user's clipboard: \n{text}"
    except Exception as e:
        print(f"[Clipboard Error]: {e}")
        return "I encountered an error trying to read the clipboard."


def check_system_diagnostics(**kwargs: Any) -> str:
    """Checks the local PC's CPU and RAM usage."""
    print("[SYSTEM] Running system diagnostics...")
    try:
        # Give the CPU a 1-second interval to calculate a true average
        cpu_usage: float = psutil.cpu_percent(interval=1)
        ram: Any = psutil.virtual_memory()
        ram_usage: float = ram.percent

        return f"System Diagnostics: The CPU is currently running at {cpu_usage} percent capacity. The system RAM is at {ram_usage} percent capacity."
    except Exception as e:
        print(f"[Diagnostics Error]: {e}")
        return "I was unable to access the system diagnostic sensors."


def analyze_screen(**kwargs: Any) -> str:
    """Takes a screenshot and uses Groq Vision to describe it."""
    print("[SYSTEM] Capturing screen for visual analysis...")
    try:
        screenshot: Any = pyautogui.screenshot()

        buffered = BytesIO()
        screenshot.save(buffered, format="JPEG", quality=80)
        img_str: str = base64.b64encode(buffered.getvalue()).decode("utf-8")

        groq_key: str | None = os.getenv("GROQ_API_KEY")
        if not groq_key:
            return "I cannot access my vision processing because the API key is missing."

        client = Groq(api_key=groq_key)

        print("[SYSTEM] Routing image to Llama 4 Scout (17B)...")
        completion: Any = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text",
                         "text": "Briefly describe what is currently on the user's screen. Do not describe the desktop layout, just the main application or content they are looking at. Keep it concise."},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_str}"}}
                    ]
                }
            ],
            temperature=0.5,
            max_tokens=150,
        )

        description: str = str(completion.choices[0].message.content)
        return f"Based on my visual analysis, {description}"

    except Exception as e:
        print(f"[Vision Error]: {e}")
        return "I encountered an error trying to process your screen."


# The scope defines what permission we are asking for (read-only calendar access)
SCOPES: list[str] = ['https://www.googleapis.com/auth/calendar']


def check_calendar(**kwargs: Any) -> str:
    """Reads the upcoming events from Google Calendar."""
    print("[SYSTEM] Accessing Google Calendar...")
    creds: Any = None

    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                return "My calendar token expired and I couldn't refresh it."
        else:
            if not os.path.exists('credentials.json'):
                return "I am missing the credentials.json file to access your Google Calendar."
            flow: Any = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)

        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    try:
        service: Any = build('calendar', 'v3', credentials=creds)

        now: str = datetime.datetime.utcnow().isoformat() + 'Z'
        events_result: Any = service.events().list(
            calendarId='primary', timeMin=now,
            maxResults=3, singleEvents=True,
            orderBy='startTime'
        ).execute()

        events: list[dict[str, Any]] = events_result.get('items', [])

        if not events:
            return "You have no upcoming events in your calendar today."

        agenda: str = "Here is what is next on your calendar: "
        for event in events:
            summary: str = event.get('summary', 'Unknown Event')
            agenda += f"{summary}. "

        return agenda

    except Exception as e:
        print(f"[Calendar Error]: {e}")
        return "I ran into an error connecting to your Google Calendar."


def add_calendar_event(summary: str, hour: int, minute: int, **kwargs: Any) -> str:
    """Adds a new event to Google Calendar."""
    print(f"[SYSTEM] Scheduling: {summary} at {hour}:{minute:02d}")
    creds: Any = None

    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                return "My calendar token expired and I couldn't refresh it."
        else:
            if not os.path.exists('credentials.json'):
                return "I am missing the credentials.json file to access your Google Calendar."
            flow: Any = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)

        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    try:
        service: Any = build('calendar', 'v3', credentials=creds)

        # Get local time and set the requested hour/minute
        now: datetime.datetime = datetime.datetime.now().astimezone()
        start_time: datetime.datetime = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

        # If the time has already passed today, assume they meant tomorrow
        if start_time < now:
            start_time += datetime.timedelta(days=1)

        # Default event duration to 1 hour
        end_time: datetime.datetime = start_time + datetime.timedelta(hours=1)

        event: dict[str, Any] = {
            'summary': summary,
            'start': {'dateTime': start_time.isoformat()},
            'end': {'dateTime': end_time.isoformat()}
        }

        service.events().insert(calendarId='primary', body=event).execute()
        return f"I have successfully scheduled {summary} for {start_time.strftime('%I:%M %p')}."

    except Exception as e:
        print(f"[Calendar Error]: {e}")
        return "I ran into an error adding the event to your Google Calendar."


def delete_calendar_event(query: str, **kwargs: Any) -> str:
    """Searches for an upcoming event by title and deletes it."""
    print(f"[SYSTEM] Searching for event to delete: {query}")
    creds: Any = None

    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)

    if not creds or not creds.valid:
        return "I'm not logged in to your calendar. Please try a 'check calendar' command first."

    try:
        service: Any = build('calendar', 'v3', credentials=creds)

        # Look at the next 10 events to find a match
        now: str = datetime.datetime.utcnow().isoformat() + 'Z'
        events_result: Any = service.events().list(
            calendarId='primary', timeMin=now,
            maxResults=10, singleEvents=True,
            orderBy='startTime'
        ).execute()

        events: list[dict[str, Any]] = events_result.get('items', [])

        target_event: dict[str, Any] | None = None
        for event in events:
            if query.lower() in event.get('summary', '').lower():
                target_event = event
                break

        if not target_event:
            return f"I couldn't find any upcoming events matching '{query}' to delete."

        event_id: str = target_event['id']
        event_summary: str = target_event.get('summary', 'Unknown Event')

        service.events().delete(calendarId='primary', eventId=event_id).execute()
        return f"Successfully deleted the event: {event_summary}."

    except Exception as e:
        print(f"[Calendar Delete Error]: {e}")
        return "I ran into an error trying to delete that event."


def sync_knowledge_base(**kwargs: Any) -> str:
    """Reads all PDFs and TXT files in the knowledge_base folder and indexes them."""
    print("[SYSTEM] Syncing Knowledge Base...")
    kb_path: str = "./knowledge_base"

    if not os.path.exists(kb_path):
        os.makedirs(kb_path)
        return "The knowledge base folder didn't exist, so I created it. Please put some files in it."

    documents: list[str] = []
    metadatas: list[dict[str, str]] = []
    ids: list[str] = []

    chunk_size: int = 1000  # Split large files into 1000-character chunks

    try:
        for filename in os.listdir(kb_path):
            file_path: str = os.path.join(kb_path, filename)
            text_content: str = ""

            if filename.endswith(".txt"):
                with open(file_path, "r", encoding="utf-8") as f:
                    text_content = f.read()
            elif filename.endswith(".pdf"):
                reader: PdfReader = PdfReader(file_path)
                for page in reader.pages:
                    extracted: str | None = page.extract_text()
                    if extracted:
                        text_content += extracted + "\n"
            else:
                continue  # Skip unsupported file types

            if not text_content.strip():
                continue

            # Chunk the text
            chunks: list[str] = [text_content[i:i + chunk_size] for i in range(0, len(text_content), chunk_size)]

            for i, chunk in enumerate(chunks):
                documents.append(chunk)
                metadatas.append({"source": filename})
                ids.append(f"{filename}_chunk_{i}")

        if not documents:
            return "I checked the knowledge base folder, but it is currently empty."

        # Upsert overwrites existing chunks with the same ID, preventing duplicates
        knowledge_collection.upsert(
            documents=documents,
            metadatas=metadatas,
            ids=ids
        )

        return f"I have successfully indexed {len(os.listdir(kb_path))} files into my memory."

    except Exception as e:
        print(f"[Knowledge Base Sync Error]: {e}")
        return "I encountered an error while trying to read your files."


def search_knowledge_base(query: str, **kwargs: Any) -> str:
    """Searches the local ChromaDB for the most relevant text chunks."""
    print(f"[SYSTEM] Searching local files for: '{query}'")
    try:
        results: dict[str, Any] = knowledge_collection.query(
            query_texts=[query],
            n_results=3  # Return the top 3 most relevant chunks
        )

        fetched_docs: list[list[str]] | None = results.get('documents')
        fetched_meta: list[list[dict[str, str]]] | None = results.get('metadatas')

        if not fetched_docs or not fetched_docs[0]:
            return "I couldn't find any relevant information in your local files."

        combined_context: str = ""
        for i in range(len(fetched_docs[0])):
            source_file: str = fetched_meta[0][i].get('source', 'Unknown File') if fetched_meta else 'Unknown File'
            snippet: str = fetched_docs[0][i]
            combined_context += f"--- From file: {source_file} ---\n{snippet}\n\n"

        return combined_context

    except Exception as e:
        print(f"[Knowledge Search Error]: {e}")
        return "I encountered an error trying to search my database."


def identify_song(**kwargs: Any) -> str:
    """Records 7 seconds of audio and checks it against the Shazam database."""
    print("[SYSTEM] Listening to the ambient music for 7 seconds...")

    fs: int = 16000
    duration: int = 7
    temp_file: str = "temp_shazam.wav"

    try:
        # 1. Record 7 seconds of audio from the microphone
        recording: Any = sd.rec(int(duration * fs), samplerate=fs, channels=1, dtype='int16')
        sd.wait()

        # 2. Save it temporarily
        sf.write(temp_file, recording, fs)

        # 3. Create a mini async function to talk to Shazam
        async def recognize() -> dict[str, Any]:
            shazam = Shazam()
            out: dict[str, Any] = await shazam.recognize(temp_file)
            return out

        # 4. Run the async function and get the result
        result: dict[str, Any] = asyncio.run(recognize())

        # Clean up the temporary file so it doesn't clutter your folder
        if os.path.exists(temp_file):
            # os.remove(temp_file)
            pass

        # 5. Parse the Shazam data
        if 'track' in result:
            title: str = result['track']['title']
            artist: str = result['track']['subtitle']
            return f"The song currently playing is {title} by {artist}."
        else:
            return "I listened closely, but I couldn't identify the song playing."

    except Exception as e:
        print(f"[Shazam Error]: {e}")
        return "I ran into an error trying to connect to the music recognition servers."


AVAILABLE_TOOLS: dict[str, Callable[..., str]] = {
    "play_youtube_video": play_youtube_video,
    "open_application": open_application,
    "manage_git": manage_git,
    "shutdown_computer": shutdown_computer,
    "sleep_computer": sleep_computer,
    "check_local_weather": check_local_weather,
    "save_memory": save_memory,
    "media_control": media_control,
    "set_timer": set_timer,
    "set_volume": set_volume,
    "cancel_all_timers": cancel_all_timers,
    "take_note": take_note,
    "search_web": search_web,
    "check_system_diagnostics": check_system_diagnostics,
    "read_clipboard": read_clipboard,
    "analyze_screen": analyze_screen,
    "check_calendar": check_calendar,
    "add_calendar_event": add_calendar_event,
    "delete_calendar_event": delete_calendar_event,
    "sync_knowledge_base": sync_knowledge_base,
    "search_knowledge_base": search_knowledge_base,
    "identify_song": identify_song
}
