import os
import time
import subprocess
import requests
from robot.libraries.BuiltIn import BuiltIn
from robot.api import logger

class VideoLibrary:
    def upload_video(self, file_path, upload_endpoint, api_key="secret123"):
        """Upload video file to the API.
        Like: curl -F "file=@video.mp4" "http://localhost:5500/upload?apikey=secret123"
        """
        if not os.path.isfile(file_path):
            raise Exception(f"Fichier vidéo '{file_path}' non trouvé.")
        with open(file_path, "rb") as f:
            files = {"file": (os.path.basename(file_path), f)}
            BuiltIn().log("Starting upload...", "INFO")

            headers = {"X-API-Key": api_key}
            response = requests.post(upload_endpoint, files=files, headers=headers)

        if int(response.status_code) >= 400:
            raise Exception(f"Error uploading video: {response.text}")
        BuiltIn().log(f"API response: {response.text}", "INFO")
        return response.json()

    def download_video(self, s3_output_key, download_endpoint, output_path, api_key="secret123"):
        """Download video file from the API.
        Like: curl -o video_encoded.mp4 "http://localhost:5500/download?s3_output_key=output/encoded_video.mp4&apikey=secret123"
        """
        url = f"{download_endpoint}&s3_output_key={s3_output_key}"
        BuiltIn().log(f"Downloading video from {url}", "INFO")
        headers = {"X-API-Key": api_key}
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            raise Exception(f"Erorr downloading video: {response.text}")
        with open(output_path, "wb") as f:
            f.write(response.content)
        BuiltIn().log(f"File downloaded to {output_path}", "INFO")

    def start_docker_compose(self, project_dir="./parallel", compose_file="./parallel/docker-compose.yml", profiles=["rabbitmq", "minio", "api", "flower", "worker-low", "worker-medium", "worker-high"]): 
        profiles_cmd = []
        for profile in profiles:
            profiles_cmd.append(f"--profile")
            profiles_cmd.append(f"{profile}")

        cmd = ["docker", "compose", "--project-directory", project_dir, "--file", compose_file] + profiles_cmd + ["up", "--build", "-d"]
        logger.console(f"Starting docker-compose with the command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise Exception(f"Failed to start docker-compose: {result.stderr}")
        return result.stdout

    def stop_docker_compose(self, project_dir="./parallel", compose_file="./parallel/docker-compose.yml", profiles=["rabbitmq", "minio", "api", "flower", "worker-low", "worker-medium", "worker-high"]):

        profiles_cmd = []
        for profile in profiles:
            profiles_cmd.append(f"--profile")
            profiles_cmd.append(f"{profile}")

        cmd = ["docker", "compose", "--project-directory", project_dir, "--file", compose_file] + profiles_cmd + ["down"]
        logger.console(f"Stopping docker-compose with the command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise Exception(f"Failed to stop docker-compose: {result.stderr}")
        return result.stdout
