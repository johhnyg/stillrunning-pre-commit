# stillrunning-pre-commit

Pre-commit hook for scanning Python and Node.js dependencies against supply chain attacks. Checks 200,000+ verified malicious packages.

[![PyPI version](https://img.shields.io/pypi/v/stillrunning-pre-commit)](https://pypi.org/project/stillrunning-pre-commit/)
[![stillrunning](https://stillrunning.io/badge/protected)](https://stillrunning.io)

> **Note:** Install via repo URL below (not yet listed in pre-commit.com registry)

## Installation

Add to your `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/johhnyg/stillrunning-pre-commit
    rev: v1.0.0
    hooks:
      - id: stillrunning
```

Then install:

```bash
pre-commit install
```

## What It Scans

- `requirements.txt`, `requirements-dev.txt`, etc.
- `package.json`, `package-lock.json`, `pnpm-lock.yaml`
- `Pipfile`, `Pipfile.lock`
- `pyproject.toml`
- `environment.yml`, `pixi.toml`
- `setup.py` (install_requires)

Browse threats: [stillrunning.io/security-advisories](https://stillrunning.io/security-advisories)

## Configuration

Create `~/.stillrunning/config.yaml`:

```yaml
token: sr_your_token_here
block_dangerous: true
block_suspicious: false
```

Or set the `STILLRUNNING_TOKEN` environment variable.

## Example Output

```
🛡️  stillrunning security scan
   Scanning 15 packages from requirements.txt

  ✅ CLEAN      requests==2.31.0
  ⚠️  SUSPICIOUS sketchy-lib==1.0.0 (score: 65)
     → Obfuscated code patterns detected
  🚫 DANGEROUS  evil-pkg==0.1.0 (score: 95)
     → Known malicious package (reverse shell)

❌ 1 dangerous package(s) found — commit blocked
```

## Free vs Paid

| Feature | Free | With Token |
|---------|------|------------|
| Scans per day | 10 | Unlimited |
| Known malicious packages | Blocked | Blocked |
| Threat feed database | Checked | Checked |
| AI analysis of unknown packages | - | 100-10000/day |

Get a token at [stillrunning.io/pricing](https://stillrunning.io/pricing)

## Options

The hook accepts these options in `.pre-commit-config.yaml`:

```yaml
hooks:
  - id: stillrunning
    stages: [commit]  # or [push] for push-time scanning
```

## Skip Hook

To skip the hook for a single commit:

```bash
SKIP=stillrunning git commit -m "message"
```

## Manual Usage

```bash
pip install stillrunning-pre-commit
stillrunning-check requirements.txt package.json
```

## License

MIT
