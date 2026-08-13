#!/usr/bin/env python3
"""Validate the native Flux notification routing contract without a cluster."""
from __future__ import annotations
import re, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
NATIVE=ROOT/'clusters/belacca-production/notifications.yaml'
ROOT_KUSTOMIZE=ROOT/'clusters/belacca-production/kustomization.yaml'
DOCS=ROOT/'docs/NOTIFICATIONS.md'

def fail(message): raise ValueError(message)
def split_documents(text): return [p for p in re.split(r'(?m)^---\s*$', text) if re.search(r'(?m)^apiVersion:', p)]
def main():
 try:
  text=NATIVE.read_text(encoding='utf-8'); docs=split_documents(text)
  if len(docs)!=6: fail(f'native notification manifest must contain exactly six resources, got {len(docs)}')
  for marker in ('platform-webhook','platform-notification-webhook','native-production','belacca-native','notification-class: diagnostic'):
   if marker not in text: fail(f'missing notification marker: {marker}')
  if text.count('secretRef:') < 2: fail('notification routing must retain diagnostic and page secret references')
  if 'notifications.yaml' not in ROOT_KUSTOMIZE.read_text(encoding='utf-8'): fail('native root does not wire notifications')
  if re.search(r'(?im)^\s*(?:address|token|password|authorization|apiKey):',text): fail('notification manifest contains credential values')
  d=DOCS.read_text(encoding='utf-8')
  for marker in ('separate diagnostic and page lanes','independent failure domain','deduplication','recovery','out of band','no endpoint'):
   if marker.lower() not in d.lower(): fail(f'notification docs missing {marker}')
 except (OSError,ValueError) as exc:
  print(f'notification validation failed: {exc}',file=sys.stderr); return 1
 print('validated native Flux notification routing contract'); return 0
if __name__=='__main__': raise SystemExit(main())
