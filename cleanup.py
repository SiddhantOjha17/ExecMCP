import shutil
import subprocess
from pathlib import Path

BASE_DIR = Path("exec_envs")

def cleanup_envs():
    for folder in BASE_DIR.glob("*"):
        if folder.is_dir():
            shutil.rmtree(folder, ignore_errors=True)

def cleanup_images():
    result = subprocess.run(
        "docker images --format '{{.Repository}}:{{.Tag}} {{.ID}}' | grep '^sandbox-'",
        shell=True, capture_output=True, text=True
    )
    for line in result.stdout.strip().splitlines():
        img_id = line.strip().split(" ")[1]
        subprocess.run(["docker", "rmi", "-f", img_id], stdout=subprocess.DEVNULL)

if __name__ == "__main__":
    cleanup_envs()
    cleanup_images()
