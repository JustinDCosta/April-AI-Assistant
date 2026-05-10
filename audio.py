"""Speech input (Faster Whisper) and speech output (Piper subprocess + sounddevice).

On Windows, CUDA DLLs bundled in the active ``venv`` may need explicit loading via
``os.add_dll_directory`` before importing GPU-backed wheels.
"""

import os
import sys
import emoji

venv_base = sys.prefix
nvidia_cublas = os.path.join(venv_base, "Lib", "site-packages", "nvidia", "cublas", "bin")
nvidia_cudnn = os.path.join(venv_base, "Lib", "site-packages", "nvidia", "cudnn", "bin")

if os.path.exists(nvidia_cublas):
    os.add_dll_directory(nvidia_cublas)
if os.path.exists(nvidia_cudnn):
    os.add_dll_directory(nvidia_cudnn)

import platform
import subprocess
import speech_recognition as sr
import sounddevice as sd
import soundfile as sf
import numpy as np
import io
from faster_whisper import WhisperModel

print("[SYSTEM] Booting up Faster-Whisper Model (medium.en) on RTX 3060...")
audio_model = WhisperModel("./whisper_model", device="cuda", compute_type="float16")

recognizer = sr.Recognizer()

print("[SYSTEM] Calibrating microphone... Please stay perfectly quiet for 2 seconds.")
with sr.Microphone() as source:
    recognizer.adjust_for_ambient_noise(source, duration=2.0)
print(f"[SYSTEM] Calibration complete! Room noise level detected at: {recognizer.energy_threshold}")

recognizer.pause_threshold = 1.0


def listen() -> str:
    """Capture microphone audio and transcribe it with the loaded Whisper model.

    ``vad_filter`` suppresses low-energy segments where Whisper tends to hallucinate
    short phrases (e.g. stock thank-you lines).

    Returns:
        Transcript text, or an empty string on timeout or failure.
    """
    with sr.Microphone() as source:
        print("\n[🎙️ April is Listening...]")
        try:
            audio = recognizer.listen(source, timeout=5, phrase_time_limit=30)
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

        text = "".join([segment.text for segment in segments])

        if text.strip():
            print(f"🗣️ You said: {text.strip()}")

        return text.strip()

    except sr.UnknownValueError:
        return ""
    except Exception as e:
        print(f"[❌ Audio Error]: {e}")
        return ""


def speak(text: str) -> None:
    """Synthesize speech with Piper (stdin WAV path) and play through sounddevice.

    Emojis and light Markdown markers are stripped because Piper and the playback
    pipeline target plain spoken output.

    Args:
        text: Full assistant reply to vocalize.

    Returns:
        None
    """
    if not text:
        return

    print(f"🤖 April: {text}")

    clean_text = emoji.replace_emoji(text, replace='')

    clean_text = clean_text.replace('*', '').replace('#', '').replace('"', '').strip()

    base_dir = os.path.dirname(os.path.abspath(__file__))
    piper_dir = os.path.join(base_dir, "piper_tts")

    voice_model = os.path.join(piper_dir, "en_US-libritts_r-medium.onnx")
    output_audio = os.path.join(base_dir, "output.wav")

    current_os = platform.system()
    if current_os == "Windows":
        piper_exe = os.path.join(piper_dir, "piper.exe")
    else:
        piper_exe = os.path.join(piper_dir, "piper")

    if not os.path.exists(piper_exe) or not os.path.exists(voice_model):
        print(f"[❌ Error] Piper executable or Voice model not found.")
        return

    try:
        piper_command = [piper_exe, "-m", voice_model, "-f", output_audio]

        subprocess.run(
            piper_command,
            input=clean_text.encode('utf-8'),
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        data, fs = sf.read(output_audio)
        silence = np.zeros(int(fs * 0.4), dtype=data.dtype)
        data_with_silence = np.concatenate((silence, data))

        sd.play(data_with_silence, fs)
        sd.wait()

    except Exception as e:
        print(f"[❌ TTS/Playback Error]: {e}")
