#!/usr/bin/env python3
import os
import sys

def main():
    queues = [q.strip() for q in os.environ.get("CELERY_QUEUES", "video").split(",") if q.strip()]
    if not queues:
        print("CELERY_QUEUES is undefined or empty.")
        sys.exit(1)

    cmd = ["celery", "-A", "tasks", "worker", "--loglevel=info", "--without-mingle", "--without-gossip", "-Q", ",".join(queues)]

    os.execvp(cmd[0], cmd)

if __name__ == "__main__":
    print("Starting worker")
    main()
