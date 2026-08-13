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
  for marker in ('platform-webhook','platform-page-webhook','native-production','belacca-native','notification-class: diagnostic'):
   if marker not in text: fail(f'missing notification marker: {marker}')
  if 'type: alertmanager' not in text: fail('Flux notifications must use the central Alertmanager receiver')
  if 'alertmanager-native.observability.svc.cluster.local:9093/api/v2/alerts/' not in text: fail('Flux notifications must target the in-cluster Alertmanager API')
  if 'notifications.yaml' not in ROOT_KUSTOMIZE.read_text(encoding='utf-8'): fail('native root does not wire notifications')
  if re.search(r'(?im)^\s*(?:token|password|authorization|apiKey):',text): fail('notification manifest contains credential values')
  for address in re.findall(r'(?im)^\s*address:\s*(\S+)', text):
   if not address.startswith('http://alertmanager-native.observability.svc.cluster.local:9093/'):
    fail('notification manifest contains an external endpoint')
  d=' '.join(DOCS.read_text(encoding='utf-8').split()).lower()
  for marker in ('separate diagnostic and page lanes','central in-cluster alertmanager','deduplication','recovery','out of band','external monitoring is intentionally deferred'):
   if ' '.join(marker.lower().split()) not in d: fail(f'notification docs missing {marker}')
 except (OSError,ValueError) as exc:
  print(f'notification validation failed: {exc}',file=sys.stderr); return 1
 print('validated native Flux notification routing contract'); return 0
if __name__=='__main__': raise SystemExit(main())
