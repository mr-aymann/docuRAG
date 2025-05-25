# utils.py

from datetime import datetime


def log_chunk_info(url, chunk_id, length):
    print(f"[CHUNK] URL: {url}, Chunk {chunk_id}, Length: {length}")


def timestamped_filename(prefix="output_", ext=".txt"):
    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{prefix}{now}{ext}"