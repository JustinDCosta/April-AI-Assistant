from google import genai

# Put your actual API key here
client = genai.Client(api_key="AIzaSyAzlMCyOa4lpYYiCl4E2cwov8r9p5c35Pg")

print("Asking Google for available models...")
try:
    # This asks Google to list every model your key is allowed to access
    for model in client.models.list():
        # We only want to see the text/chat models
        if "generateContent" in model.supported_actions:
            print(f"✅ Allowed Model: {model.name}")
except Exception as e:
    print(f"❌ Error: {e}")
