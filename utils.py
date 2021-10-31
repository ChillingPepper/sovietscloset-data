from datetime import datetime


def log(source, message):
    timestamp = datetime.utcnow().isoformat(timespec="seconds")
    print(f"[{timestamp}Z] [{source}] {message}")
