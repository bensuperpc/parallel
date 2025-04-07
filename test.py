import requests
import time
import os

API_URL = "http://localhost:5500"
API_KEY = "secret123"
UPLOAD_ENDPOINT = f"{API_URL}/upload?apikey={API_KEY}"
DOWNLOAD_ENDPOINT = f"{API_URL}/download?apikey={API_KEY}"
VIDEO_FILE = "video.mp4"
OUTPUT_FILENAME = "video_encoded.mp4"

def upload_video(file_path):
    with open(file_path, "rb") as f:
        files = {"file": (os.path.basename(file_path), f)}
        print("Sending request to upload video...")
        response = requests.post(UPLOAD_ENDPOINT, files=files)
    
    if response.status_code != 202:
        raise Exception(f"Error during upload: {response.text}")
    
    data = response.json()
    print("API response:", data)
    return data

def download_video(s3_output_key, output_path):
    url = f"{DOWNLOAD_ENDPOINT}&s3_output_key={s3_output_key}"
    print("Trying to download the encoded video from:", url)
    response = requests.get(url)
    
    if response.status_code != 200:
        raise Exception(f"Error during download: {response.text}")
    
    with open(output_path, "wb") as f:
        f.write(response.content)
    print(f"File downloaded successfully to {output_path}")

def main():
    if not os.path.isfile(VIDEO_FILE):
        raise Exception(f"Video file {VIDEO_FILE} not found.")
    
    result = upload_video(VIDEO_FILE)
    s3_output_key = result.get("s3_output_key")
    task_id = result.get("task_id")
    
    if not s3_output_key or not task_id:
        raise Exception("Missing s3_output_key or task_id in the response.")
    
    print(f"Task ID: {task_id}")
    
    print("Waiting 60 sec for the task to complete...")
    time.sleep(60)
    
    download_video(s3_output_key, OUTPUT_FILENAME)

if __name__ == "__main__":
    main()
