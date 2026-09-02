#!/usr/bin/env python3
"""Validate native recovery and game-day contracts without cluster access."""
from __future__ import annotations
import re
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CONTRACT=ROOT/'docs/BACKUP-CONTRACT.md'
DRILLS=ROOT/'docs/GAME-DAY-DRILLS.md'

def main():
    try:
        contract=CONTRACT.read_text(encoding='utf-8')
        drills=DRILLS.read_text(encoding='utf-8')
        for marker in ('14 daily verified backups','TLS is required','pong-backup-object-store','pong-backup-encryption','pong-backup-restore-object-store','CronJobs use externally managed gates','pong-api-data'):
            if marker not in contract: raise ValueError(f'missing backup marker: {marker}')
        for marker in ('# Native production game-day drills','belacca-native','Drill 1 — one public edge unavailable','one control-plane/server unavailable','Longhorn','rollback'):
            if marker not in drills: raise ValueError(f'missing native drill marker: {marker}')
        if re.search(r'(?im)^\s*(?:address|endpoint|bucket|access-key-id|secret-access-key|kms-key-id):\s*https?://|^\s*(?:access-key-id|secret-access-key|kms-key-id):\s*[^<`\s]+', contract):
            raise ValueError('backup contract contains credential or endpoint values')
        if 'do not upload' not in contract.lower() and 'does not upload' not in contract.lower():
            raise ValueError('backup contract must state that the helper does not upload')
    except (OSError, ValueError) as exc:
        print(f'recovery contract validation failed: {exc}', file=sys.stderr); return 1
    print('validated native recovery contract and game-day drill markers'); return 0
if __name__=='__main__': raise SystemExit(main())
