"""Hybrid routing and cloud fallback for April.

Loads Groq credentials from the environment, injects long-term memory into the system
prompt, routes tool calls through a local Ollama model, then completes replies via
Groq with stepped fallbacks when the API or primary model is unavailable.
"""

import ollama
import os
import json
from typing import Any, cast

from dotenv import load_dotenv
from groq import Groq
from tools import AVAILABLE_TOOLS

load_dotenv()

_groq_key = os.getenv("GROQ_API_KEY")
if not _groq_key or not str(_groq_key).strip():
    raise RuntimeError(
        "GROQ_API_KEY is not set. Copy `.env.example` to `.env` and add your API key "
        "(see README)."
    )
groq_client = Groq(api_key=str(_groq_key).strip())

memories_text = ""
if os.path.exists("memory.json"):
    with open("memory.json", "r", encoding="utf-8") as f:
        memories = cast(list[str], json.load(f))
        memories_text = "\n".join(memories)

system_instruction = f"""
You are April, a highly capable AI assistant. You process data instantly and speak concisely.
Speak like a real person, use natural phrasing, and be casually supportive.
Keep your spoken responses short and conversational. Do not ramble.

CRITICAL RULE: DO NOT use emojis. You are a voice-driven assistant, and emojis ruin text-to-speech.

Here are facts you MUST remember about the user:
{memories_text}
"""

# Rolling window of recent turns for Groq and router context (each turn is user + assistant).
chat_history: list[dict[str, str]] = []
MAX_HISTORY = 10

OLLAMA_TOOLS: list[dict[str, Any]] = [
    {
        'type': 'function',
        'function': {
            'name': 'search_web',
            'description': 'Call this tool when you need to look up real-time facts, news, currently relevant info, or anything you do not know the answer to.',
            'parameters': {
                'type': 'object',
                'properties': {'query': {'type': 'string', 'description': 'The exact search engine query.'}},
                'required': ['query']
            }
        }
    },
    {
        'type': 'function',
        'function': {
            'name': 'play_youtube_video',
            'description': 'CRITICAL MANDATORY: Call this tool IMMEDIATELY whenever the user asks to "play" a song, video, artist, or movie on YouTube.',
            'parameters': {
                'type': 'object',
                'properties': {'query': {'type': 'string', 'description': 'The name of the song or video.'}},
                'required': ['query']
            }
        }
    },
    {
        'type': 'function',
        'function': {
            'name': 'open_application',
            'description': 'Call this tool when the user asks to open an application, game, or software.',
            'parameters': {
                'type': 'object',
                'properties': {'app_name': {'type': 'string', 'description': 'The name of the application.'}},
                'required': ['app_name']
            }
        }
    },
    {
        'type': 'function',
        'function': {
            'name': 'check_local_weather',
            'description': 'Call this ONLY when the user explicitly asks for the weather, temperature, or forecast. DO NOT call this if the user is just talking about their day, taking a bath, or having a normal conversation.',
            'parameters': {'type': 'object', 'properties': {}, 'required': []}
        }
    },
    {
        'type': 'function',
        'function': {
            'name': 'sleep_computer',
            'description': 'Call this tool when the user asks to put the computer or PC to sleep.',
            'parameters': {'type': 'object', 'properties': {}, 'required': []}
        }
    },
    {
        'type': 'function',
        'function': {
            'name': 'save_memory',
            'description': 'Call this to remember a permanent fact about the user.',
            'parameters': {
                'type': 'object',
                'properties': {'fact': {'type': 'string', 'description': 'The exact fact to remember.'}},
                'required': ['fact']
            }
        }
    },
    {
        'type': 'function',
        'function': {
            'name': 'set_volume',
            'description': 'Call this ONLY when the user asks to set the volume to a specific absolute number or percentage.',
            'parameters': {
                'type': 'object',
                'properties': {'level': {'type': 'integer', 'description': 'Volume percentage (0 to 100).'}},
                'required': ['level']
            }
        }
    },
    {
        'type': 'function',
        'function': {
            'name': 'media_control',
            'description': 'Call this to change system volume relative to where it is now, or to skip/pause tracks.',
            'parameters': {
                'type': 'object',
                'properties': {'action': {'type': 'string',
                                          'enum': ['play_pause', 'next', 'previous', 'mute', 'volume_up',
                                                   'volume_down']}},
                'required': ['action']
            }
        }
    },
    {
        'type': 'function',
        'function': {
            'name': 'take_note',
            'description': 'Call this tool ANY TIME the user asks you to "take a note", "write this down", or "remind me to".',
            'parameters': {
                'type': 'object',
                'properties': {'note_text': {'type': 'string', 'description': 'The exact text of the note.'}},
                'required': ['note_text']
            }
        }
    },
    {
        'type': 'function',
        'function': {
            'name': 'set_timer',
            'description': 'Call this to set a timer or alarm.',
            'parameters': {
                'type': 'object',
                'properties': {'minutes': {'type': 'integer', 'description': 'The amount of time in minutes'}},
                'required': ['minutes']
            }
        }
    }
]


def process_intent(user_input: str) -> str:
    """Route the utterance through local tool execution, then cloud completion with fallbacks.

    Local Qwen proposes tool calls. Non-search tools may yield an immediate concatenated
    reply without updating ``chat_history``. Search results extend the user prompt; Groq
    then completes (primary model, smaller Groq model, then local Qwen). ``chat_history``
    is updated only when this completion path runs.

    Args:
        user_input: Normalized command text from the main loop.

    Returns:
        Spoken response string for TTS.
    """
    global chat_history
    print(f"[SYSTEM] Local Router (Qwen) analyzing: '{user_input}'")

    try:
        qwen_messages = [
            {
                'role': 'system',
                'content': 'You are a strict tool router. ONLY call a tool if the user explicitly requests a physical action (like opening an app, setting volume, searching the web, or checking weather). If the user asks a question about themselves, their past, their memory, or just wants to chat, DO NOT call any tools.'
            }
        ]
        # Recent turns give short continuity without growing the router context without bound.
        qwen_messages.extend(chat_history[-2:])
        qwen_messages.append({'role': 'user', 'content': user_input})

        response: Any = ollama.chat(
            model='qwen2.5:3b',
            messages=qwen_messages,
            tools=OLLAMA_TOOLS
        )
    except Exception as e:
        print(f"[❌ OLLAMA ROUTER ERROR]: {e}")
        return "My local routing system is offline."

    web_context = ""
    spoken_replies = []

    if response.get('message', {}).get('tool_calls'):
        for tool_call in response['message']['tool_calls']:
            func_name = tool_call['function']['name']
            func_args = tool_call['function']['arguments']

            if func_name in AVAILABLE_TOOLS:
                print(f"[SYSTEM] Executing Tool: {func_name}")
                try:
                    action_result = AVAILABLE_TOOLS[func_name](**func_args)

                    if func_name == "search_web":
                        web_context = action_result
                        print("[SYSTEM] Web data retrieved. Passing to Groq Cloud...")
                    else:
                        spoken_replies.append(action_result)
                except Exception as e:
                    print(f"[❌ TOOL ERROR]: {e}")
                    spoken_replies.append(f"I ran into an error trying to use {func_name}.")

        # Non-search tools already produced user-facing strings; skip cloud call when no synthesis is needed.
        if spoken_replies and not web_context:
            return " ".join(spoken_replies)

    print("[SYSTEM] Routing to Groq (Llama 3.3 70B)...")
    final_prompt = user_input
    if web_context:
        final_prompt = (
            f"The user asked: '{user_input}'. Here is data from the web: \n{web_context}\n\n"
            "Based ONLY on this data, answer the question conversationally."
        )

    messages_payload = [{"role": "system", "content": system_instruction}]
    messages_payload.extend(chat_history)
    messages_payload.append({"role": "user", "content": final_prompt})

    final_reply = ""

    try:
        chat_completion = groq_client.chat.completions.create(
            messages=messages_payload,  # type: ignore
            model="llama-3.3-70b-versatile",
            temperature=0.7,
            stream=False
        )
        reply_content = chat_completion.choices[0].message.content  # type: ignore
        final_reply = str(reply_content) if reply_content else "I couldn't formulate a response."

    except Exception as e:
        print(f"[⚠️ 70B LIMIT HIT]: {e}")
        print("[SYSTEM] Shifting to Groq 8B Instant fallback...")

        try:
            chat_completion = groq_client.chat.completions.create(
                messages=messages_payload,  # type: ignore
                model="llama-3.1-8b-instant",
                temperature=0.7,
                stream=False
            )
            reply_content = chat_completion.choices[0].message.content  # type: ignore
            final_reply = str(reply_content) if reply_content else "I couldn't formulate a response."

        except Exception as e2:
            print(f"[❌ 8B ERROR]: {e2}")
            print("[SYSTEM] Groq fully unreachable! Falling back to Local GPU (Qwen)...")
            try:
                fallback_response: Any = ollama.chat(
                    model='qwen2.5:3b',
                    messages=messages_payload  # type: ignore
                )
                final_reply = fallback_response.get('message', {}).get('content', "Local brain failed.")
            except Exception as local_e:
                print(f"[❌ LOCAL FALLBACK ERROR]: {local_e}")
                final_reply = "Both my cloud and local brains are currently offline."

    chat_history.append({"role": "user", "content": user_input})
    chat_history.append({"role": "assistant", "content": final_reply})

    if len(chat_history) > MAX_HISTORY:
        chat_history = chat_history[-MAX_HISTORY:]

    return final_reply
