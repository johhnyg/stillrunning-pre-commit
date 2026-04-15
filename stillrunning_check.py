#!/usr/bin/env python3
"""
stillrunning pre-commit hook — Scan dependencies for supply chain attacks.

Usage:
    stillrunning-check requirements.txt package.json
"""
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

API_URL = "https://stillrunning.io/api/github-action/scan"
CONFIG_FILE = Path.home() / ".stillrunning" / "config.json"

# Terminal colors
RED = "\033[91m"
YELLOW = "\033[93m"
GREEN = "\033[92m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def load_config() -> dict:
    """Load config from ~/.stillrunning/config.json"""
    try:
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE) as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def parse_requirements_txt(content: str) -> list:
    """Parse requirements.txt format."""
    packages = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        if "#" in line:
            line = line.split("#")[0].strip()
        if line:
            packages.append(line)
    return packages


def parse_package_json(content: str) -> list:
    """Parse package.json dependencies."""
    packages = []
    try:
        data = json.loads(content)
        for dep_type in ["dependencies", "devDependencies", "peerDependencies"]:
            deps = data.get(dep_type, {})
            for name, version in deps.items():
                version = re.sub(r'^[\^~>=<]', '', str(version))
                packages.append(f"{name}@{version}")
    except json.JSONDecodeError:
        pass
    return packages


def parse_pipfile(content: str) -> list:
    """Parse Pipfile packages section."""
    packages = []
    in_packages = False
    for line in content.splitlines():
        line = line.strip()
        if line == "[packages]" or line == "[dev-packages]":
            in_packages = True
            continue
        if line.startswith("[") and in_packages:
            in_packages = False
            continue
        if in_packages and "=" in line:
            name = line.split("=")[0].strip().strip('"')
            if name:
                packages.append(name)
    return packages


def parse_pyproject_toml(content: str) -> list:
    """Parse pyproject.toml dependencies (simplified)."""
    packages = []
    in_deps = False
    for line in content.splitlines():
        line = line.strip()
        if "dependencies" in line and "=" in line:
            in_deps = True
            continue
        if in_deps:
            if line.startswith("]"):
                in_deps = False
                continue
            # Extract package name from "package>=1.0.0" or '"package"'
            match = re.search(r'["\']?([a-zA-Z0-9_-]+)', line)
            if match:
                packages.append(match.group(1))
    return packages


def parse_file(filepath: str) -> list:
    """Parse a dependency file and return list of packages."""
    path = Path(filepath)
    if not path.exists():
        return []

    content = path.read_text()
    name = path.name.lower()

    if name.endswith(".txt"):
        return parse_requirements_txt(content)
    elif name == "package.json" or name == "package-lock.json":
        return parse_package_json(content)
    elif name == "pipfile":
        return parse_pipfile(content)
    elif name == "pyproject.toml":
        return parse_pyproject_toml(content)
    elif name == "setup.py":
        # Extract from install_requires
        match = re.search(r'install_requires\s*=\s*\[(.*?)\]', content, re.DOTALL)
        if match:
            packages = []
            for pkg in re.findall(r'["\']([^"\']+)["\']', match.group(1)):
                packages.append(pkg)
            return packages
    return []


def call_api(packages: list, token: str) -> dict:
    """Call stillrunning.io API."""
    # Get repo name from git if available
    repo = "local"
    try:
        import subprocess
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            url = result.stdout.strip()
            # Extract owner/repo from URL
            match = re.search(r'[:/]([^/]+/[^/]+?)(?:\.git)?$', url)
            if match:
                repo = match.group(1)
    except Exception:
        pass

    payload = json.dumps({
        "packages": packages,
        "repo": repo,
        "token": token
    }).encode()

    req = urllib.request.Request(
        API_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "stillrunning-pre-commit/1.0"
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode() if e.fp else ""
        return {"error": f"API error: {e.code} - {error_body}"}
    except urllib.error.URLError as e:
        # Network error - allow commit but warn
        return {"error": f"Network error: {e.reason}", "offline": True}
    except Exception as e:
        return {"error": f"Request failed: {e}"}


def print_result(result: dict):
    """Print formatted result for a package."""
    verdict = result.get("verdict", "UNKNOWN")
    package = result.get("package", "unknown")
    version = result.get("version", "")
    score = result.get("score", 0)
    reason = result.get("reason", "")

    pkg_display = f"{package}=={version}" if version and version != "latest" else package

    if verdict == "DANGEROUS":
        print(f"  {RED}{BOLD}🚫 DANGEROUS{RESET}  {pkg_display} {DIM}(score: {score}){RESET}")
        if reason:
            print(f"     {DIM}→ {reason}{RESET}")
    elif verdict == "SUSPICIOUS":
        print(f"  {YELLOW}⚠️  SUSPICIOUS{RESET} {pkg_display} {DIM}(score: {score}){RESET}")
        if reason:
            print(f"     {DIM}→ {reason}{RESET}")
    elif verdict == "UNKNOWN":
        print(f"  {DIM}❓ UNKNOWN{RESET}    {pkg_display}")
        if reason:
            print(f"     {DIM}→ {reason}{RESET}")
    else:
        print(f"  {GREEN}✅ CLEAN{RESET}      {pkg_display}")


def main(argv=None):
    """Main entry point."""
    args = argv if argv is not None else sys.argv[1:]

    if not args:
        print(f"{YELLOW}stillrunning: No files to check{RESET}")
        return 0

    # Load config
    config = load_config()
    token = config.get("token", "") or os.environ.get("STILLRUNNING_TOKEN", "")
    block_dangerous = config.get("block_dangerous", True)
    block_suspicious = config.get("block_suspicious", False)

    # Parse all files
    all_packages = []
    files_checked = []

    for filepath in args:
        packages = parse_file(filepath)
        if packages:
            all_packages.extend(packages)
            files_checked.append(filepath)

    # Deduplicate
    all_packages = list(set(all_packages))

    if not all_packages:
        return 0

    print(f"\n{BOLD}🛡️  stillrunning security scan{RESET}")
    print(f"{DIM}   Scanning {len(all_packages)} packages from {', '.join(files_checked)}{RESET}\n")

    # Call API
    result = call_api(all_packages, token)

    if "error" in result:
        if result.get("offline"):
            print(f"{YELLOW}⚠️  Network unavailable — skipping scan{RESET}")
            print(f"{DIM}   {result['error']}{RESET}\n")
            return 0
        print(f"{RED}Error: {result['error']}{RESET}")
        return 1

    # Process results
    summary = result.get("summary", {})
    dangerous = summary.get("dangerous", 0)
    suspicious = summary.get("suspicious", 0)
    clean = summary.get("clean", 0)
    unknown = summary.get("unknown", 0)

    # Print results (only non-clean packages to keep output short)
    results = result.get("results", [])
    non_clean = [r for r in results if r.get("verdict") != "CLEAN"]

    if non_clean:
        for r in non_clean:
            print_result(r)
        print()

    # Summary
    if dangerous > 0:
        print(f"{RED}{BOLD}❌ {dangerous} dangerous package(s) found — commit blocked{RESET}")
    elif suspicious > 0 and block_suspicious:
        print(f"{YELLOW}{BOLD}⚠️  {suspicious} suspicious package(s) found — commit blocked{RESET}")
    elif suspicious > 0:
        print(f"{YELLOW}⚠️  {suspicious} suspicious package(s) — review recommended{RESET}")

    if unknown > 0 and not token:
        print(f"\n{DIM}💡 {unknown} packages not AI-scanned. Add token to ~/.stillrunning/config.json{RESET}")
        print(f"{DIM}   Get a token at https://stillrunning.io/pricing{RESET}")

    if dangerous == 0 and (not block_suspicious or suspicious == 0):
        print(f"{GREEN}✅ Scan passed{RESET} — {clean} clean, {suspicious} suspicious, {unknown} unknown\n")
        return 0

    print()
    return 1


if __name__ == "__main__":
    sys.exit(main())
