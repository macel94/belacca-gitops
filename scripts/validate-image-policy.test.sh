#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
python3 "$root/scripts/validate-image-policy.py"

fixture_dir=$(mktemp -d)
trap 'rm -rf "$fixture_dir"' EXIT
cp "$root/tests/fixtures/invalid-production-image.yaml" "$fixture_dir/invalid.yaml"

if python3 "$root/scripts/validate-image-policy.py" --manifest-root "$fixture_dir"; then
  echo 'negative image policy test failed: mutable image was accepted' >&2
  exit 1
fi

echo 'negative image policy test rejected mutable first-party image'
