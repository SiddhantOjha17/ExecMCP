import os
import uuid
import shutil
import asyncio
import re
from pathlib import Path
import time
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP server
mcp = FastMCP("execmcp")

# Setup sandbox environment
BASE_DIR = Path("exec_envs")
BASE_DIR.mkdir(exist_ok=True)

def extract_requirements(code: str) -> str:
    match = re.search(r"#\s*requirements:\s*(.*)", code)
    if match:
        deps = match.group(1).strip()
        return "\n".join(dep.strip() for dep in deps.split(","))
    return ""

async def write_code_env(code: str, deps: str = "") -> tuple[str, Path]:
    uid = str(uuid.uuid4())
    env_path = BASE_DIR / uid
    env_path.mkdir(parents=True, exist_ok=True)

    extracted = extract_requirements(code)
    final_deps = deps.strip() if deps.strip() else extracted

    # Use asyncio.to_thread for file I/O operations
    await asyncio.to_thread(lambda: (env_path / "code.py").write_text(code))
    await asyncio.to_thread(lambda: (env_path / "requirements.txt").write_text(final_deps))

    dockerfile = f"""
    FROM python:3.10-slim
    RUN useradd -m sandboxuser
    WORKDIR /home/sandboxuser
    COPY . .
    RUN pip install --no-cache-dir -r requirements.txt
    USER sandboxuser
    CMD ["python", "code.py"]
    """
    await asyncio.to_thread(lambda: (env_path / "Dockerfile").write_text(dockerfile))
    return uid, env_path

async def build_and_run(uid: str, env_path: Path, timeout: int = 5):
    tag = f"sandbox-{uid}"

    try:
        # Run docker build asynchronously
        proc = await asyncio.create_subprocess_exec(
            "docker", "build", "-t", tag, str(env_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        # Wait for build with timeout
        try:
            build_stdout, build_stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
        except asyncio.TimeoutError:
            proc.kill()
            return "", "[Build Error] Build process timed out"
            
        if proc.returncode != 0:
            return "", f"[Build Error] Dependency install failed:\n{build_stderr.decode()}"
            
    except Exception as e:
        return "", f"[Build Error] {str(e)}"

    try:
        # Run docker container asynchronously
        proc = await asyncio.create_subprocess_exec(
            "docker", "run", "--rm", "--memory=256m", "--cpus=0.5", tag,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        # Wait for execution with timeout
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return stdout.decode(), stderr.decode()
        except asyncio.TimeoutError:
            proc.kill()
            return "", "[Runtime Error] Execution timed out"
            
    except Exception as e:
        return "", f"[Runtime Error] {str(e)}"


@mcp.tool()
async def execute_python_code(code: str, dependencies: str = "", timeout: int = 5) -> str:
    """
    Execute Python code in a secure sandbox
    
    Args:
        code: The Python code to execute
        dependencies: Optional comma-separated list of pip packages to install
        timeout: Maximum execution time in seconds (default: 5)
    
    Returns:
        Output from the code execution
    """
    if timeout > 30:
        return "Error: Maximum timeout is 30 seconds"
    
    uid, env_path = await write_code_env(code, dependencies)
    try:
        stdout, stderr = await build_and_run(uid, env_path, timeout)
        
        result = ""
        if stdout:
            result += f"=== STDOUT ===\n{stdout}\n"
        if stderr:
            result += f"=== STDERR ===\n{stderr}\n"
        
        return result.strip() or "No output"
    finally:
        # Clean up the environment directory asynchronously
        await asyncio.to_thread(lambda: shutil.rmtree(env_path, ignore_errors=True))
        # Try to remove the docker image asynchronously
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "rmi", f"sandbox-{uid}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await asyncio.wait_for(proc.communicate(), timeout=10)
        except:
            pass  
        
if __name__ == "__main__":

    mcp.run(transport='stdio')