#!/usr/bin/env python3
"""Extract literal Prometheus config/rules from the Kubernetes ConfigMap YAML."""

import argparse
from pathlib import Path

parser = argparse.ArgumentParser(description="Extract Prometheus config/rules from a GitOps observability ConfigMap.")
parser.add_argument(
    "--historical",
    action="store_true",
    help="extract from the retired vmi3474918 tree for audit/reference only",
)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
source = root / "clusters" / ("vmi3474918" if args.historical else "belacca-production") / "observability" / "config.yaml"
text = source.read_text()
config = text.split("  prometheus.yml: |\n", 1)[1].split("\n  prometheus.rules.yml: |", 1)[0]
rules = text.split("  prometheus.rules.yml: |\n", 1)[1]

def extract(value: str) -> str:
    return "\n".join(line[4:] if line.startswith("    ") else line for line in value.splitlines()) + "\n"

Path("/tmp/prometheus.yml").write_text(extract(config))
Path("/tmp/prometheus.rules.yml").write_text(extract(rules))
print(f"extracted {'historical/reference' if args.historical else 'native production'} Prometheus config from {source}")
