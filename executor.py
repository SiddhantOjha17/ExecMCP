import os
import uuid
import shutil
import subprocess
import re
from pathlib import Path

BASE_DIR = Path("exec_envs")
BASE_DIR.mkdir(exist_ok=True)

def extract_requirements(code: str) -> str:
    match = re.search(r"#\s*requirements:\s*(.*)", code)
    if match:
        deps = match.group(1).strip()
        return "\n".join(dep.strip() for dep in deps.split(","))
    return ""

def write_code_env(code: str, deps: str = "") -> tuple[str, Path]:
    uid = str(uuid.uuid4())
    env_path = BASE_DIR / uid
    env_path.mkdir(parents=True, exist_ok=True)

    extracted = extract_requirements(code)
    final_deps = deps.strip() if deps.strip() else extracted

    (env_path / "code.py").write_text(code)
    (env_path / "requirements.txt").write_text(final_deps)

    dockerfile = f"""
    FROM python:3.10-slim
    RUN useradd -m sandboxuser
    WORKDIR /home/sandboxuser
    COPY . .
    RUN pip install --no-cache-dir -r requirements.txt
    USER sandboxuser
    CMD ["python", "code.py"]
    """
    (env_path / "Dockerfile").write_text(dockerfile)
    return uid, env_path

def build_and_run(uid: str, env_path: Path, timeout: int = 5):
    tag = f"sandbox-{uid}"

    try:
        build = subprocess.run(
            ["docker", "build", "-t", tag, str(env_path)],
            capture_output=True,
            check=True,
            timeout=60
        )
    except subprocess.CalledProcessError as e:
        return "", f"[Build Error] Dependency install failed:\n{e.stderr.decode()}"

    try:
        result = subprocess.run(
            ["docker", "run", "--rm", "--memory=256m", "--cpus=0.5", tag],
            capture_output=True,
            timeout=timeout
        )
        return result.stdout.decode(), result.stderr.decode()
    except subprocess.TimeoutExpired:
        return "", "[Runtime Error] Execution timed out"
    except Exception as e:
        return "", f"[Runtime Error] {str(e)}"
