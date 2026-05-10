import httpx
import json
import time

API_URL = "http://localhost:8000/api/v1/sessions"

SESSIONS = [
    "User: I prefer concise answers. Agent: Noted. User: I work in fintech.",
    "User: I'm usually available mornings. I'm based in London.",
    "User: Actually I'd prefer detailed explanations going forward.",
    "User: I've moved to Singapore recently.",
    "User: I prefer phone over email for urgent issues."
]

def run_seed():
    user_id = "user_001"
    
    with httpx.Client() as client:
        for idx, text in enumerate(SESSIONS):
            print(f"---\nSeeding Session {idx+1}...")
            start = time.time()
            data = {
                "user_id": user_id,
                "conversation": text
            }
            try:
                response = client.post(API_URL, json=data, timeout=60.0)
                response.raise_for_status()
                res_data = response.json()
                print(f"Success! {json.dumps(res_data, indent=2)}")
                print(f"Duration: {time.time() - start:.2f}s")
            except Exception as e:
                print(f"Failed to seed session {idx+1}: {e}")
                if hasattr(e, "response") and e.response is not None:
                    print(e.response.text)

if __name__ == "__main__":
    run_seed()