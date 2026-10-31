#!/usr/bin/env python3
"""Validate JSON asset manifest records against registered repositories."""
import argparse, json, re, sys
from pathlib import Path

def validate(obj, repos):
    errors=[]
    required=('id','kind','domain','status','source_uri','license','provenance','delivery')
    for key in required:
        if key not in obj: errors.append(f'missing required field {key}')
    provenance=obj.get('provenance')
    if provenance not in ('authored','library','generated'):
        if not isinstance(provenance,dict) or any(k not in ('generated_by','tool','model') or not isinstance(v,str) for k,v in provenance.items()): errors.append('provenance must be authored, library, generated, or a structured provenance object')
    if not str(obj.get('license','')).strip(): errors.append('license must be non-empty')
    if not (obj.get('source_rev') or obj.get('hash')): errors.append('source_rev or hash is required')
    delivery=obj.get('delivery')
    if not isinstance(delivery,dict) or not delivery.get('repo') or not delivery.get('path'): errors.append('delivery requires repo and path')
    else:
        if delivery['repo'] not in repos: errors.append(f"delivery repo {delivery['repo']} is not registered")
        path=delivery['path'].replace('\\','/')
        if path.startswith('/') or re.match(r'^[A-Za-z]:',path) or any(x=='..' for x in path.split('/')): errors.append('delivery path must stay inside a registered repo')
    return errors

def main():
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8")
    ap=argparse.ArgumentParser(); ap.add_argument('target',type=Path); ap.add_argument('--registry',type=Path); args=ap.parse_args()
    reg=json.loads(args.registry.read_text(encoding='utf-8')) if args.registry else {'repos':{'authoring':{},'client':{},'server':{}}}
    paths=[args.target] if args.target.is_file() else sorted(args.target.rglob('*.asset.json'))
    failed=0
    for path in paths:
        try: obj=json.loads(path.read_text(encoding='utf-8')); errors=validate(obj,reg['repos'])
        except Exception as e: errors=[str(e)]
        if errors:
            failed+=1
            for e in errors: print(f'FAIL {path}: {e}')
        else: print(f'PASS {path}')
    if not paths: print(f'PASS asset-manifest: 0 records in {args.target}')
    print(f'asset-manifest: {len(paths)} checked, {len(paths)-failed} passed, {failed} failed')
    return 1 if failed else 0
if __name__=='__main__': sys.exit(main())
