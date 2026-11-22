from datetime import datetime, timezone

def bucket(timestamp, zone):
    return datetime.fromisoformat(timestamp).astimezone(timezone.utc).date().isoformat()
