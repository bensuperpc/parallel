#!/usr/bin/env python3
import os
import sys
import urllib.request
import tempfile
import shutil
import subprocess
from time import sleep

def main():
    queues = os.environ.get("CELERY_QUEUES", "video").split(",")
    if not queues:
        print("CELERY_QUEUES is undefined or empty.")
        sys.exit(1)

    queues_param = ["-Q", ",".join(q.strip() for q in queues if q.strip())]

    tasks_url = os.environ.get("CELERY_TASKS_URL")
    if not tasks_url:
        print("CELERY_TASKS_URL is undefined or empty.")
        sys.exit(1)
    print(f"Downloading tasks script from {tasks_url}")
    
    for attempt in range(10):
        try:
            with urllib.request.urlopen(tasks_url) as r, open("/app/tasks.py", "wb") as f:
                shutil.copyfileobj(r, f)
            break
        except Exception as e:
            print(f"Download failed (attempt {attempt + 1}/10): {e}")
            sleep(2)
    else:
        print("Failed to download tasks script after multiple attempts.")
        sys.exit(1)
    print(f"Script downloaded to /app/tasks.py")

    cmd = ["celery", "-A", "tasks", "worker", "--loglevel=info"] + queues_param

    os.execvp(cmd[0], cmd)

if __name__ == "__main__":
    print("Starting worker")
    main()
