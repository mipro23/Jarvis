import pyttsx3

engine = pyttsx3.init()

for i, voice in enumerate(engine.getProperty("voices")):
    print(f"{i}: {voice.name}")
    print(f"   ID: {voice.id}")
    print(f"   Languages: {voice.languages}")
