import httpx

data = {
    "sessions": [
        "User: I prefer concise answers. Agent: Noted. User: I work in fintech.",
        "User: I'm usually available mornings. I'm based in London.",
        "User: Actually I'd prefer detailed explanations going forward.",
        "User: I've moved to Singapore recently.",
        "User: I prefer phone over email for urgent issues."
    ],
    "thresholds": [0.70, 0.82, 0.90]
}

response = httpx.post("http://localhost:8000/api/v1/admin/threshold-sweep", json=data, timeout=300)
try:
    print(response.json())
except Exception as e:
    print(response.text)
