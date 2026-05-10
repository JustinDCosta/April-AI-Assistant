"""Voice-driven main loop for April.

Listens for wake words or conversation-mode phrases, extracts the spoken command,
logs exchanges to disk, and delegates reasoning to ``brain.process_intent``. Uses
literal phrase checks for destructive OS actions so behavior stays deterministic.
"""

from audio import listen, speak
from brain import process_intent
import datetime
import os

WAKE_WORDS: list[str] = [
    "april", "babe", "darling", "computer", "hey april", "system"
]

CONVO_START_PHRASES: list[str] = [
    "let's talk", "lets talk", "let's chat", "lets chat",
    "let's have a conversation", "lets have a conversation",
    "start conversation mode", "start convo mode",
    "convo mode on", "conversation mode on"
]

CONVO_END_PHRASES: list[str] = [
    "stop conversation mode", "stop convo mode", "end conversation mode",
    "turn off conversation mode", "turn off convo mode",
    "end chat", "that's all", "that is all", "exit conversation mode",
    "stop listening"
]


def log_chat(role: str, text: str) -> None:
    """Append a single log line to ``chat_history.md`` in Markdown format.

    Args:
        role: Label printed in the Markdown line (typically ``You`` or ``April``).
        text: Utterance text; empty strings are skipped.

    Returns:
        None
    """
    if not text:
        return

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %I:%M %p")

    with open("chat_history.md", "a", encoding="utf-8") as f:
        # Append creates an empty file first; guard ensures the title block is written once.
        if os.path.getsize("chat_history.md") == 0:
            f.write("# 📖 April Conversation Logs\n\n")

        f.write(f"**[{timestamp}] {role}:** {text}\n\n")


def run_assistant() -> None:
    """Run the perpetual listen-process-speak loop until shutdown or exit phrase.

    Flow: optional conversation-mode toggles, wake-word gating outside that mode,
    command cleanup, then ``process_intent`` and TTS. OS shutdown uses a fixed
    transcript match so it cannot be triggered by paraphrasing.

    Returns:
        None
    """
    speak("HI, I am April! All systems are online.")

    in_conversation_mode = False

    while True:
        transcription = listen().lower().strip()

        if not transcription:
            continue

        # Whisper often emits stock closing phrases on silence; dropping them avoids junk commands.
        if transcription in ["thank you", "thank you.", "thanks", "thank you!", "thanks for watching.",
                             "thank you very much."]:
            continue

        # Require this exact transcript so shutdown is never inferred from similar wording.
        if transcription == "april shut down the computer please":
            speak("Shutting down the computer now. Goodbye.")
            os.system("shutdown /s /t 5")
            break

        if in_conversation_mode and any(phrase in transcription for phrase in CONVO_END_PHRASES):
            in_conversation_mode = False
            print("[SYSTEM] Exiting Conversation Mode.")
            speak("Conversation mode ended. Just call my name if you need me.")
            continue

        if not in_conversation_mode and any(phrase in transcription for phrase in CONVO_START_PHRASES):
            in_conversation_mode = True
            print("[SYSTEM] Entering Conversation Mode.")
            speak("Conversation mode activated. I'm all ears.")
            continue

        command = ""

        if in_conversation_mode:
            command = transcription
            for word in WAKE_WORDS:
                command = command.replace(word, "")
        else:
            detected_wake_word = None
            for word in WAKE_WORDS:
                if word in transcription:
                    detected_wake_word = word
                    break

            if detected_wake_word:
                print(f"[SYSTEM] Wake word triggered: '{detected_wake_word}'")
                command = transcription.replace(detected_wake_word, "")
            else:
                continue

        for char in [".", ",", "!", "?"]:
            command = command.replace(char, "")
        command = command.strip()

        if "shut down core systems" in command:
            speak("Taking core systems offline. Goodbye.")
            break

        if not command:
            if not in_conversation_mode:
                speak("Yes, I am here. What do you need?")
            continue

        log_chat("You", command)

        response = process_intent(command)

        log_chat("April", response)

        speak(response)


if __name__ == "__main__":
    run_assistant()
