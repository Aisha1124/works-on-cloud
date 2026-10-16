"""Deploy KampungCart to Cloud Run with `gcloud run deploy --source .`.

Cross-platform (macOS / Windows): plain Python, no extra dependencies. One-time project setup
(APIs, service account, secrets) is in infra/README.md; run that first.

Usage:
    uv run python scripts/deploy.py --dry-run      # print the gcloud command, change nothing
    uv run python scripts/deploy.py                # build in Cloud Build and deploy
    uv run python scripts/deploy.py --project my-proj --gemini-model gemini-3.8-flash

BASE_URL is worked out before the first deploy: Cloud Run service URLs are deterministic
(https://SERVICE-PROJECT_NUMBER.REGION.run.app), so the MCP host allow-list and the UCP profile
are right on the very first revision.
"""

import argparse
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULTS = {
    "service": "kampungcart",
    "region": "asia-southeast1",
    "sa_name": "kampungcart-run",
    "gemini_model": "gemini-3.8-flash",
    "gemini_secret": "gemini-api-key",
    "owner_secret": "owner-key",
}


def gcloud() -> str:
    exe = shutil.which("gcloud")
    if not exe:
        sys.exit("gcloud is not on PATH. Install the Google Cloud CLI first.")
    return exe


def gcloud_value(*args: str) -> str:
    out = subprocess.run([gcloud(), *args], capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit(f"gcloud {' '.join(args)} failed:\n{out.stderr.strip()}")
    return out.stdout.strip()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--project", help="GCP project id (default: gcloud's current project)")
    p.add_argument("--region", default=DEFAULTS["region"])
    p.add_argument("--service", default=DEFAULTS["service"])
    p.add_argument("--service-account", help=f"default: {DEFAULTS['sa_name']}@PROJECT.iam...")
    p.add_argument("--gemini-model", default=DEFAULTS["gemini_model"])
    p.add_argument("--base-url", help="Override BASE_URL (e.g. a custom domain)")
    p.add_argument("--dry-run", action="store_true", help="Print the command and exit")
    return p.parse_args()


def main() -> None:
    a = parse_args()
    project = a.project or gcloud_value("config", "get-value", "project")
    if not project:
        sys.exit("No project. Pass --project or run: gcloud config set project PROJECT_ID")
    number = gcloud_value("projects", "describe", project, "--format=value(projectNumber)")
    base_url = a.base_url or f"https://{a.service}-{number}.{a.region}.run.app"
    sa = a.service_account or f"{DEFAULTS['sa_name']}@{project}.iam.gserviceaccount.com"

    env = {
        "GEMINI_MODEL": a.gemini_model,
        "GCP_PROJECT_ID": project,
        "GCP_REGION": a.region,
        "BASE_URL": base_url,
        # Firestore/GCS stores are not implemented yet; see infra/README.md "Known limits".
        "STORE_BACKEND": "local",
    }
    secrets = {
        "GEMINI_API_KEY": f"{DEFAULTS['gemini_secret']}:latest",
        "OWNER_KEY": f"{DEFAULTS['owner_secret']}:latest",
    }

    cmd = [
        gcloud(), "run", "deploy", a.service,
        "--source", ".",
        "--project", project,
        "--region", a.region,
        "--service-account", sa,
        # Public: AI agents and shoppers call it without Google auth. Owner routes are
        # protected in the app by X-Owner-Key.
        "--allow-unauthenticated",
        "--set-env-vars", ",".join(f"{k}={v}" for k, v in env.items()),
        "--set-secrets", ",".join(f"{k}={v}" for k, v in secrets.items()),
        # Risk explanations run as background tasks after the response is sent; with CPU
        # throttling they would stall. Instance-based billing keeps CPU on.
        "--no-cpu-throttling",
        "--cpu-boost",
        "--cpu", "1",
        "--memory", "1Gi",
        # One instance while STORE_BACKEND=local: data lives on that instance's disk and the
        # rate limiter is in memory. min=1 also avoids a cold start during the demo.
        "--min-instances", "1",
        "--max-instances", "1",
        "--concurrency", "40",
        "--timeout", "120",
        "--labels", "app=kampungcart",
        "--quiet",
    ]

    print("Project:  ", project)
    print("BASE_URL: ", base_url)
    print("Runs as:  ", sa)
    print("\n" + " ".join(shlex.quote(c) for c in [Path(cmd[0]).name, *cmd[1:]]) + "\n")
    if a.dry_run:
        return
    sys.exit(subprocess.run(cmd, cwd=REPO_ROOT).returncode)


if __name__ == "__main__":
    main()
