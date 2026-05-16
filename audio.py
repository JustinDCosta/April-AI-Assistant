"""Speech input (Faster Whisper) and speech output (Piper subprocess + sounddevice)."""

import os
import sys
import emoji
import platform
import subprocess
import speech_recognition as sr
import sounddevice as sd
import soundfile as sf
import numpy as np
import io
import time
import queue
import keyboard
from faster_whisper import WhisperModel
from typing import Any

# ==========================================
# ⚙️ CONFIGURATION
# Change this to 'scroll lock', 'f13', etc.
PTT_HOTKEY: str = "f8"
# ==========================================

venv_base: str = sys.prefix
nvidia_cublas: str = os.path.join(venv_base, "Lib", "site-packages", "nvidia", "cublas", "bin")
nvidia_cudnn: str = os.path.join(venv_base, "Lib", "site-packages", "nvidia", "cudnn", "bin")

if os.path.exists(nvidia_cublas):
    os.add_dll_directory(nvidia_cublas)
if os.path.exists(nvidia_cudnn):
    os.add_dll_directory(nvidia_cudnn)

print("[SYSTEM] Booting up Faster-Whisper Model (medium.en) on RTX 3060...")
audio_model: WhisperModel = WhisperModel("./whisper_model", device="cuda", compute_type="float16")

recognizer: sr.Recognizer = sr.Recognizer()

print("[SYSTEM] Calibrating microphone... Please stay perfectly quiet for 2 seconds.")
with sr.Microphone() as source:
    recognizer.adjust_for_ambient_noise(source, duration=2.0)
print(f"[SYSTEM] Calibration complete! Room noise level detected at: {recognizer.energy_threshold}")

recognizer.pause_threshold = 1.0


def listen_ptt(key: str) -> str:
    """Records audio continuously as long as the key is held, bypassing silence timeouts."""
    print(f"\n[🎙️ WALKIE-TALKIE MODE: Holding '{key}'...]")
    q: queue.Queue[np.ndarray] = queue.Queue()

    def callback(indata: np.ndarray, frames: int, time_info: Any, status: Any) -> None:
        if status:
            print(status, file=sys.stderr)
        q.put(indata.copy())

    fs: int = 16000
    try:
        # Start raw recording directly from the microphone
        with sd.InputStream(samplerate=fs, channels=1, dtype='int16', callback=callback):
            while keyboard.is_pressed(key):
                time.sleep(0.05)
    except Exception as e:
        print(f"[❌ Audio stream error]: {e}")
        return ""

    # User released the key, stitch the audio chunks together
    audio_data: list[np.ndarray] = []
    while not q.empty():
        audio_data.append(q.get())

    if not audio_data:
        return ""

    audio_np: np.ndarray = np.concatenate(audio_data, axis=0)

    # Convert the raw audio array into a WAV format in memory for Whisper
    wav_io = io.BytesIO()
    sf.write(wav_io, audio_np, fs, format='WAV', subtype='PCM_16')
    wav_io.seek(0)

    print("[⚙️ Processing PTT Audio...]")
    try:
        segments, _ = audio_model.transcribe(
            wav_io,
            beam_size=5,
            vad_filter=False,  # Turned off so it captures your exact held duration
        )
        text: str = "".join([segment.text for segment in segments])

        if text.strip():
            print(f"🗣️ You said (PTT): {text.strip()}")
        return text.strip()
    except Exception as e:
        print(f"[❌ PTT Error]: {e}")
        return ""


def listen() -> str:
    """Capture microphone audio. Routes to PTT if hotkey is pressed, otherwise standard ambient listen."""

    # 1. Check if the user is already holding the button before we start standard listening
    if keyboard.is_pressed(PTT_HOTKEY):
        sd.stop()  # Instantly kill any residual TTS audio playing
        return listen_ptt(PTT_HOTKEY)

    # 2. Standard hands-free listening
    with sr.Microphone() as source:
        print("\n[🎙️ April is Listening...]")
        try:
            # We lowered the timeout to 1 second. This allows the script to quickly loop
            # and check if you pressed the hotkey, keeping the system highly responsive.
            audio: sr.AudioData = recognizer.listen(source, timeout=1, phrase_time_limit=30)
        except sr.WaitTimeoutError:
            return ""

    try:
        print("[⚙️ Processing Audio...]")
        wav_data = io.BytesIO(audio.get_wav_data())

        segments, _ = audio_model.transcribe(
            wav_data,
            beam_size=5,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500)
        )

        text: str = "".join([segment.text for segment in segments])

        if text.strip():
            print(f"🗣️ You said: {text.strip()}")

        return text.strip()

    except sr.UnknownValueError:
        return ""
    except Exception as e:
        print(f"[❌ Audio Error]: {e}")
        return ""


def speak(text: str) -> None:
    """Synthesize speech with Piper and play through sounddevice. Interruptible by hotkey."""
    if not text:
        return

    print(f"🤖 April: {text}")
    clean_text: str = emoji.replace_emoji(text, replace='')
    clean_text = clean_text.replace('*', '').replace('#', '').replace('"', '').strip()

    base_dir: str = os.path.dirname(os.path.abspath(__file__))
    piper_dir: str = os.path.join(base_dir, "piper_tts")
    voice_model: str = os.path.join(piper_dir, "en_US-libritts_r-medium.onnx")
    output_audio: str = os.path.join(base_dir, "output.wav")

    current_os: str = platform.system()
    piper_exe: str = os.path.join(piper_dir, "piper.exe") if current_os == "Windows" else os.path.join(piper_dir,
                                                                                                       "piper")

    if not os.path.exists(piper_exe) or not os.path.exists(voice_model):
        print(f"[❌ Error] Piper executable or Voice model not found.")
        return

    try:
        piper_command: list[str] = [piper_exe, "-m", voice_model, "-f", output_audio]

        subprocess.run(
            piper_command,
            input=clean_text.encode('utf-8'),
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        data: np.ndarray
        fs: int
        data, fs = sf.read(output_audio)
        silence: np.ndarray = np.zeros(int(fs * 0.4), dtype=data.dtype)
        data_with_silence: np.ndarray = np.concatenate((silence, data))

        # Start playing the audio in the background
        sd.play(data_with_silence, fs)

        # Instead of sd.wait() which blocks everything, we use a monitored timer loop
        duration: float = len(data_with_silence) / fs
        start_time: float = time.time()

        while time.time() - start_time < duration:
            # If the user presses the interrupt button while she is talking...
            if keyboard.is_pressed(PTT_HOTKEY):
                print("\n[🛑 April Interrupted by User!]")
                sd.stop()  # Kill the audio instantly
                break
            time.sleep(0.05)

    except Exception as e:
        print(f"[❌ TTS/Playback Error]: {e}")
