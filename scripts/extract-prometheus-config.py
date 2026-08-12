#!/usr/bin/env python3
"""Extract literal Prometheus config/rules from the Kubernetes ConfigMap YAML."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def extract_config(source: Path, output_prefix: str) -> None:
    text = source.read_text()
    config = text.split("  prometheus.yml: |\n", 1)[1].split("\n  prometheus.rules.yml: |", 1)[0]
    rules = text.split("  prometheus.rules.yml: |\n", 1)[1]

    def extract(value: str) -> str:
        return "\n".join(
            line[4:] if line.startswith("    ") else line
            for line in value.splitlines()
        ) + "\n"

    extracted_rules = extract(rules)
    Path(f"/tmp/{output_prefix}-prometheus.yml").write_text(extract(config))
    Path(f"/tmp/{output_prefix}-prometheus.rules.yml").write_text(extracted_rules)
    if output_prefix == "native":
        start = extracted_rules.index("  - name: belacca-native-slo-recording")
        end = extracted_rules.index("  - name: belacca-native-slo-source-readiness")
        test_rules = extracted_rules[start:end].replace(
            "    interval: 1h\n", "    interval: 24h\n", 1
        )
        Path("/tmp/native-slo-test.rules.yml").write_text("groups:\n" + test_rules)


extract_config(ROOT / "clusters/belacca-production/observability/config.yaml", "native")
extract_config(ROOT / "clusters/vmi3474918/observability/config.yaml", "historical")
# Keep the original paths for existing local workflows, but make them point at
# the retired tree explicitly so no command can mistake it for native evidence.
Path("/tmp/prometheus.yml").write_text(Path("/tmp/historical-prometheus.yml").read_text())
Path("/tmp/prometheus.rules.yml").write_text(Path("/tmp/historical-prometheus.rules.yml").read_text())
