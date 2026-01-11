import requests
import json


def parse_sse_event(event_text: str) -> dict:
    lines = event_text.strip().split('\n')
    event = {}
    for line in lines:
        if ':' in line:
            key, value = line.split(':', 1)
            event[key.strip()] = value.strip()
    return event


def consume_stream(url: str = "http://localhost:8000/stream"):
    print(f"Connecting to {url}...")
    
    try:
        response = requests.get(url, headers={"Accept": "text/event-stream"}, stream=True)
        print(f"Connected! Status: {response.status_code}\n")
        
        buffer = ""
        for chunk in response.iter_content(chunk_size=None, decode_unicode=True):
            if chunk:
                buffer += chunk
                while "\n\n" in buffer:
                    event_text, buffer = buffer.split("\n\n", 1)
                    if event_text.strip():
                        event = parse_sse_event(event_text)
                        print(f"[{event.get('event', 'unknown')}] ID: {event.get('id', 'N/A')}")
                        if 'data' in event:
                            try:
                                data = json.loads(event['data'])
                                print(f"  Data: {json.dumps(data, indent=2)}\n")
                            except:
                                print(f"  Data: {event['data']}\n")
    except KeyboardInterrupt:
        print("\nDisconnected")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    consume_stream()
