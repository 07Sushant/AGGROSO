"""Deploy backend/ to the Hugging Face Docker Space and wait until it is healthy.

Reads HF_TOKEN and HF_SPACE_ID from .env.deploy, and the three app secrets from .env.
Secret values are never printed.

    python scripts/deploy_hf.py              # deploy + wait for /api/health
    python scripts/deploy_hf.py --no-wait
    python scripts/deploy_hf.py --wait-only  # just poll the hosted health endpoint

Requires huggingface_hub (in backend/requirements-dev.txt).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
APP_SECRETS = ("GROQ_API_KEY", "GEMINI_API_KEY", "DATABASE_URL")
SPACE_VARIABLES = {
    "APP_ENV": "production",
    "FAULT_INJECTION_ENABLED": "true",
    "CORS_ORIGINS": "http://localhost:5173",
}
IGNORE_PATTERNS = [
    "tests/*",
    "tests/**",
    ".venv/*",
    ".venv/**",
    "**/__pycache__/**",
    "__pycache__/**",
    "*.pyc",
    ".pytest_cache/**",
    ".ruff_cache/**",
    "*.db",
    ".env",
    ".env.*",
    "requirements-dev.txt",
]


def read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def git_sha() -> str:
    out = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True,
        check=True,
    )
    sha = out.stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--", "backend"], cwd=ROOT, capture_output=True,
        text=True, check=True,
    ).stdout.strip()
    return f"{sha}-dirty" if dirty else sha


def space_url(api: HfApi, space_id: str) -> str:
    info = api.space_info(space_id)
    host = getattr(info, "host", None)
    if host:
        return host.rstrip("/")
    return "https://" + space_id.replace("/", "-").replace("_", "-").replace(".", "-").lower() \
        + ".hf.space"


def wait_for_health(base_url: str, timeout_s: int) -> bool:
    deadline = time.time() + timeout_s
    url = f"{base_url}/api/health"
    last = ""
    while time.time() < deadline:
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(url, timeout=60) as res:  # noqa: S310 - fixed https URL
                body = json.loads(res.read().decode("utf-8"))
            latency = int((time.perf_counter() - started) * 1000)
            summary = (
                f"status={body.get('status')} db={body['db']['status']} "
                f"ai={body['ai']['status']} version={body.get('version')} latency={latency}ms"
            )
            if summary != last:
                print(f"  health: {summary}")
                last = summary
            if body["db"]["status"] == "ok" and body["ai"]["status"] == "primary":
                return True
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as exc:
            msg = f"  waiting ({type(exc).__name__})"
            if msg != last:
                print(msg)
                last = msg
        time.sleep(10)
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-wait", action="store_true")
    parser.add_argument("--wait-only", action="store_true")
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args()

    deploy_env = read_env_file(ROOT / ".env.deploy")
    token, space_id = deploy_env.get("HF_TOKEN"), deploy_env.get("HF_SPACE_ID")
    if not token or not space_id:
        print("HF_TOKEN and HF_SPACE_ID must be set in .env.deploy", file=sys.stderr)
        return 2
    api = HfApi(token=token)

    if not args.wait_only:
        app_env = read_env_file(ROOT / ".env")
        missing = [k for k in APP_SECRETS if not app_env.get(k)]
        if missing:
            print(f"missing in .env: {', '.join(missing)}", file=sys.stderr)
            return 2

        for key in APP_SECRETS:
            api.add_space_secret(space_id, key, app_env[key])
            print(f"secret set: {key}")
        for key, value in SPACE_VARIABLES.items():
            api.add_space_variable(space_id, key, value)
            print(f"variable set: {key}={value}")

        sha = git_sha()
        (BACKEND / "GIT_SHA").write_text(sha + "\n", encoding="utf-8")
        print(f"GIT_SHA={sha}; uploading backend/ to {space_id}")
        api.upload_folder(
            folder_path=str(BACKEND),
            repo_id=space_id,
            repo_type="space",
            commit_message=f"Deploy backend {sha}",
            delete_patterns=["*"],
            ignore_patterns=IGNORE_PATTERNS,
        )
        print("upload complete; the Space is rebuilding")

    base_url = space_url(api, space_id)
    print(f"hosted URL: {base_url}")
    if args.no_wait:
        return 0
    ok = wait_for_health(base_url, args.timeout)
    print("healthy" if ok else "timed out waiting for a healthy /api/health")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
