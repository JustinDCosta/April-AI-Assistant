"""Hybrid routing and cloud fallback for April.

Loads Groq credentials from the environment, injects long-term memory into the system
prompt, routes tool calls through a local Ollama model, then completes replies via
Groq with stepped fallbacks when the API or primary model is unavailable.
"""

import ollama
import os
import json
import datetime
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
            'description': 'Call this ONLY when the user explicitly asks for the weather, temperature, or forecast.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'city': {
                        'type': 'string',
                        'description': 'The city to check the weather for. Defaults to Sevran if not specified.'
                    }
                },
                'required': []
            }
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
            'description': 'Call this to pause, play, unpause, resume, replay, or skip media tracks, as well as change system volume relative to where it is now.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'action': {
                        'type': 'string',
                        'enum': ['play_pause', 'next', 'previous', 'mute', 'volume_up', 'volume_down']
                    }
                },
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
    },
    {
        'type': 'function',
        'function': {
            'name': 'cancel_all_timers',
            'description': 'Call this tool ANY TIME the user asks you to cancel, stop, or remove a timer, alarm, or reminder.',
            'parameters': {'type': 'object', 'properties': {}, 'required': []}
        }
    },
    {
        'type': 'function',
        'function': {
            'name': 'read_clipboard',
            'description': 'Call this tool ANY TIME the user asks you to read, summarize, or analyze what they just copied, or asks what is on their clipboard.',
            'parameters': {'type': 'object', 'properties': {}, 'required': []}
        }
    },
    {
        'type': 'function',
        'function': {
            'name': 'check_system_diagnostics',
            'description': 'Call this tool when the user asks about computer performance, CPU usage, RAM, or why the computer is running slow.',
            'parameters': {'type': 'object', 'properties': {}, 'required': []}
        }
    },
    {
        'type': 'function',
        'function': {
            'name': 'analyze_screen',
            'description': 'Call this tool ONLY when the user EXPLICITLY asks you to "look at my screen", "what am I looking at", or "read the screen". CRITICAL: DO NOT call this tool if the user is just talking about their day or making casual conversation.',
            'parameters': {'type': 'object', 'properties': {}, 'required': []}
        }
    },
    {
        'type': 'function',
        'function': {
            'name': 'check_calendar',
            'description': 'Call this tool when the user asks about their schedule, their calendar, their day, or upcoming events.',
            'parameters': {'type': 'object', 'properties': {}, 'required': []}
        }
    },
    {
        'type': 'function',
        'function': {
            'name': 'add_calendar_event',
            'description': 'Call this tool when the user asks to schedule something, add an event to their calendar, or set an appointment.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'summary': {'type': 'string', 'description': 'The name or title of the event.'},
                    'hour': {'type': 'integer',
                             'description': 'The hour of the event in 24-hour format (0-23). Example: 5 PM is 17.'},
                    'minute': {'type': 'integer', 'description': 'The minute of the event (0-59).'}
                },
                'required': ['summary', 'hour', 'minute']
            }
        }
    },
    {
        'type': 'function',
        'function': {
            'name': 'delete_calendar_event',
            'description': 'Call this tool when the user wants to cancel, remove, or delete an event or appointment from their calendar.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {'type': 'string', 'description': 'A keyword or title of the event to delete.'}
                },
                'required': ['query']
            }
        }
    },
    {
        'type': 'function',
        'function': {
            'name': 'sync_knowledge_base',
            'description': 'Call this tool when the user asks you to read, scan, update, or sync their local files, university folders, or knowledge base.',
            'parameters': {'type': 'object', 'properties': {}, 'required': []}
        }
    },
    {
        'type': 'function',
        'function': {
            'name': 'search_knowledge_base',
            'description': 'Call this tool when the user asks a question about their personal files, documents, PDFs, university notes, or syllabus.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {'type': 'string', 'description': 'The exact search query to look for in the documents.'}
                },
                'required': ['query']
            }
        }
    },
    {
        'type': 'function',
        'function': {
            'name': 'identify_song',
            'description': 'Call this tool when the user asks what song is playing, asks you to identify the music, or asks you to "Shazam" a track.',
            'parameters': {'type': 'object', 'properties': {}, 'required': []}
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
        qwen_messages: list[dict[str, str]] = [
            {
                'role': 'system',
                'content': (
                    "You are a strict tool router. ONLY call a tool if the user explicitly requests a physical action "
                    "(like searching the web, checking weather, taking a screenshot, or managing media). "
                    "CRITICAL RULE: If the user is just making a conversational statement (e.g., 'I went to the gym', 'I had a good day'), "
                    "telling a story, or asking for advice, you MUST NOT call any tools. Just output normal text."
                )
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

    tool_context: str = ""
    spoken_replies: list[str] = []

    # Define tools that gather context for the LLM to summarize/analyze
    context_tools: list[str] = ["search_web", "read_clipboard", "check_system_diagnostics", "search_knowledge_base",
                                "check_local_weather"]

    if response.get('message', {}).get('tool_calls'):
        for tool_call in response['message']['tool_calls']:
            func_name: str = tool_call['function']['name']
            func_args: dict[str, Any] = tool_call['function']['arguments']

            if func_name in AVAILABLE_TOOLS:
                print(f"[SYSTEM] Executing Tool: {func_name}")
                try:
                    action_result: str = AVAILABLE_TOOLS[func_name](**func_args)

                    if func_name in context_tools:
                        tool_context += f"Data from {func_name}:\n{action_result}\n\n"
                        print(f"[SYSTEM] Data from {func_name} retrieved. Passing to Groq Cloud...")
                    else:
                        spoken_replies.append(action_result)
                except Exception as e:
                    print(f"[❌ TOOL ERROR]: {e}")
                    spoken_replies.append(f"I ran into an error trying to use {func_name}.")

        # Non-context tools already produced user-facing strings; skip cloud call when no synthesis is needed.
        if spoken_replies and not tool_context:
            return " ".join(spoken_replies)

    print("[SYSTEM] Routing to Groq (Llama 3.3 70B)...")
    final_prompt: str = user_input

    if tool_context:
        final_prompt = (
            f"The user asked: '{user_input}'. Here is the data you requested from your tools:\n{tool_context}\n\n"
            "Read the user's prompt and use this data to answer, summarize, or explain as requested."
        )

    # Generate the live date and time for this specific exact turn
    live_time: str = datetime.datetime.now().strftime("%A, %B %d, %Y at %I:%M %p")

    # Inject it into the base system instruction
    dynamic_system_prompt: str = f"{system_instruction}\n\nCRITICAL SYSTEM FACT - The current live Date and Time is: {live_time}"

    messages_payload: list[dict[str, str]] = [{"role": "system", "content": dynamic_system_prompt}]
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
