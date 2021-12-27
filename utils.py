from datetime import datetime


def log(source: str, message: str) -> None:
    timestamp = datetime.utcnow().isoformat(timespec="seconds")
    print(f"[{timestamp}Z] [{source}] {message}")
