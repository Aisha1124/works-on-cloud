"""Break-glass manual deploy: build the image locally, push it, and roll out a new revision.

Normal deploys go through GitHub Actions (.github/workflows/deploy.yml). Use this only when CI
is unavailable. Like CI, it changes ONLY the image; env vars, secrets, scaling and probes are
owned by Terraform (infra/terraform/run.tf), so nothing here can drift from it.

Cross-platform (macOS / Windows). Needs Docker (with buildx) and gcloud, logged in.

Usage:
    python scripts/deploy.py --dry-run
    python scripts/deploy.py
"""

import argparse
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PROJECT = "kampungcart-prod"
REGION = "asia-southeast1"
SERVICE = "kampungcart"


def tool(name: str) -> str:
    exe = shutil.which(name)
    if not exe:
        sys.exit(f"{name} is not on PATH.")
    return exe


def run(cmd: list[str], dry: bool, **kw) -> str:
    print("$", " ".join(shlex.quote(c) for c in [Path(cmd[0]).name, *cmd[1:]]))
    if dry:
        return ""
    out = subprocess.run(cmd, cwd=REPO_ROOT, text=True, **kw)
    if out.returncode != 0:
        sys.exit(f"Failed (exit {out.returncode}).")
    return out.stdout or ""


def main() -> None:
    p = argparse.ArgumentParser(description="Break-glass manual deploy (image only).")
    p.add_argument("--project", default=PROJECT)
    p.add_argument("--region", default=REGION)
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()

    gcloud, docker, git = tool("gcloud"), tool("docker"), tool("git")
    sha = subprocess.run([git, "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT,
                         capture_output=True, text=True).stdout.strip() or "unknown"
    dirty = subprocess.run([git, "status", "--porcelain"], cwd=REPO_ROOT,
                           capture_output=True, text=True).stdout.strip()
    tag = f"manual-{sha}{'-dirty' if dirty else ''}"
    image = f"{a.region}-docker.pkg.dev/{a.project}/kampungcart/app:{tag}"

    token = "" if a.dry_run else subprocess.run(
        [gcloud, "auth", "print-access-token"], capture_output=True, text=True).stdout.strip()
    run([docker, "login", "-u", "oauth2accesstoken", "--password-stdin",
         f"https://{a.region}-docker.pkg.dev"], a.dry_run, input=token)
    # Cloud Run runs linux/amd64; Apple Silicon builds arm64 by default.
    run([docker, "buildx", "build", "--platform", "linux/amd64", "-t", image, "--push", "."],
        a.dry_run)
    run([gcloud, "run", "deploy", SERVICE, "--project", a.project, "--region", a.region,
         "--image", image, "--quiet"], a.dry_run)
    run([gcloud, "run", "services", "update-traffic", SERVICE, "--project", a.project,
         "--region", a.region, "--to-latest", "--quiet"], a.dry_run)


if __name__ == "__main__":
    main()
