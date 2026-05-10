"""Side-effect tools invoked by the local router (Ollama).

Maps spoken intents to OS actions: applications, media keys, volume, timers, notes,
web search, and weather. Paths in ``APP_DIRECTORY`` and ``PROJECT_DIRECTORY`` are
host-specific and must be edited per deployment.
"""

from typing import Callable

from pycaw.pycaw import AudioUtilities
from ddgs import DDGS

import webbrowser
import subprocess
import urllib.request
import urllib.parse
import re
import os
import json
import threading
import time
import winsound
import pyautogui
import datetime

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


def check_local_weather() -> str:
    """Resolve coarse location via IP, then fetch current conditions from Open-Meteo.

    Browser-like headers reduce odd failures from endpoints that filter generic clients.
    WMO weather codes are mapped manually because the API returns numeric codes only.

    Returns:
        User-facing weather summary or an error string.
    """
    print("[SYSTEM] Detecting location via IP...")
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json'
        }

        loc_req = urllib.request.Request("https://get.geojs.io/v1/ip/geo.json", headers=headers)
        with urllib.request.urlopen(loc_req) as response:
            location_data = json.loads(response.read().decode())

        city = location_data.get("city", "your city")
        lat = location_data.get("latitude")
        lon = location_data.get("longitude")

        if not lat or not lon:
            return "I couldn't detect your exact location, sorry!"

        print(f"[SYSTEM] Location found: {city} ({lat}, {lon})")

        weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
        weather_req = urllib.request.Request(weather_url, headers=headers)

        with urllib.request.urlopen(weather_req) as response:
            weather_data = json.loads(response.read().decode())

        current = weather_data.get("current_weather", {})
        temp_c = current.get("temperature", 0)

        temp_f = round((temp_c * 9 / 5) + 32, 1)

        weather_code = current.get("weathercode", 0)
        conditions = {
            0: "clear skies", 1: "mostly clear", 2: "partly cloudy", 3: "overcast",
            45: "foggy", 48: "foggy", 51: "light drizzle", 53: "moderate drizzle",
            55: "heavy drizzle", 61: "slight rain", 63: "moderate rain", 65: "heavy rain",
            71: "slight snow", 73: "moderate snow", 75: "heavy snow", 95: "thunderstorms"
        }
        condition_text = conditions.get(weather_code, "mixed conditions")

        return f"Currently in {city}, it is {temp_c} degrees Celsius, or {temp_f} Fahrenheit, with {condition_text}."

    except Exception as e:
        print(f"[❌ Weather Error]: {e}")
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


def timer_thread(minutes: int) -> None:
    """Sleep then emit audible alerts (daemon worker).

    Args:
        minutes: Delay before the alarm fires.
    """
    time.sleep(minutes * 60)
    print("\n[⏰ TIMER DONE!]")
    for _ in range(3):
        winsound.Beep(1000, 500)
        time.sleep(0.1)


def set_timer(minutes: int) -> str:
    """Start ``timer_thread`` as a daemon so the main listener loop keeps running.

    Args:
        minutes: Delay before the alarm fires.

    Returns:
        User-facing confirmation string.
    """
    print(f"[SYSTEM] Starting {minutes} minute background timer...")
    t = threading.Thread(target=timer_thread, args=(minutes,))
    t.daemon = True
    t.start()
    return f"I have set a timer for {minutes} minutes."


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
    "take_note": take_note,
    "search_web": search_web
}
