#!/usr/bin/env python3
"""Extract literal Prometheus config/rules from the Kubernetes ConfigMap YAML."""

from pathlib import Path

source = Path(__file__).resolve().parents[1] / "clusters/belacca-production/observability/config.yaml"
text = source.read_text()
config = text.split("  prometheus.yml: |\n", 1)[1].split("\n  prometheus.rules.yml: |", 1)[0]
rules = text.split("  prometheus.rules.yml: |\n", 1)[1]

def extract(value: str) -> str:
    return "\n".join(line[4:] if line.startswith("    ") else line for line in value.splitlines()) + "\n"

Path("/tmp/prometheus.yml").write_text(extract(config))
Path("/tmp/prometheus.rules.yml").write_text(extract(rules))
