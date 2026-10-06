"""Check out and patch the upstream packages needed by the Pixi environment.

Run with system Python before `pixi install`. Existing checkout edits are never
discarded; a checkout at a different revision must be reconciled manually.
"""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def git(checkout, *args, check=True):
    return subprocess.run(
        ["git", "-C", str(checkout), *args],
        check=check,
        capture_output=True,
        text=True,
    )


def pending_patches(checkout, patches):
    """Check a patch stack without changing the checkout or its local edits."""
    # Later patches may change the context of earlier ones. Unwind applied
    # patches in reverse order in a disposable copy before checking the stack.
    with tempfile.TemporaryDirectory(prefix="xviewlite-patches-") as folder:
        probe = Path(folder) / "source"
        shutil.copytree(checkout, probe, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        applied = set()
        for patch in reversed(patches):
            if git(probe, "apply", "--reverse", "--check", patch, check=False).returncode == 0:
                git(probe, "apply", "--reverse", patch)
                applied.add(patch)
        # Validate every patch before making any changes to the real checkout.
        for patch in patches:
            git(probe, "apply", "--check", patch)
            git(probe, "apply", patch)
        return [patch for patch in patches if patch not in applied]


def prepare():
    sources = json.loads((ROOT / "patches/sources.json").read_text())
    for name, source in sources.items():
        checkout = ROOT / ".vendor" / name
        if not checkout.exists():
            checkout.mkdir(parents=True)
            git(checkout, "init")
            git(checkout, "remote", "add", "origin", source["url"])
        head = git(checkout, "rev-parse", "--verify", "HEAD", check=False)
        if head.returncode:
            git(checkout, "fetch", "--depth=1", "origin", source["rev"])
            git(checkout, "checkout", "--detach", "FETCH_HEAD")
        elif head.stdout.strip() != source["rev"]:
            raise RuntimeError(f"{checkout} has a different revision; refusing to overwrite it")

        patches = [str(ROOT / name) for name in source["patches"]]
        pending = pending_patches(checkout, patches)
        for patch_name, patch in zip(source["patches"], patches):
            if patch not in pending:
                print(f"{name}: {patch_name} already applied")
                continue
            git(checkout, "apply", "--check", patch)
            git(checkout, "apply", patch)
            print(f"{name}: applied {patch_name} to {source['rev'][:12]}")


if __name__ == "__main__":
    try:
        prepare()
    except subprocess.CalledProcessError as exc:
        raise SystemExit(exc.stderr) from exc
