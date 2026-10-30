"""Domain-specific 2D art production quality checks."""
import hashlib
import json
import os
import re
import struct
from pathlib import Path, PurePosixPath

from _api import Result


def _spec(item):
    return item.get('spec') if isinstance(item.get('spec'), dict) else {}


def _dimensions(path):
    with path.open('rb') as stream:
        head=stream.read(32)
    if head.startswith(b'\x89PNG\r\n\x1a\n') and len(head)>=26:
        w,h=struct.unpack('>II',head[16:24]); color=head[25]
        return w,h,'png',color in (4,6)
    if head.startswith(b'\xff\xd8'):
        with path.open('rb') as stream:
            stream.read(2)
            while True:
                byte=stream.read(1)
                if not byte: break
                if byte!=b'\xff': continue
                marker=stream.read(1)
                while marker==b'\xff': marker=stream.read(1)
                if marker in (b'\xd8',b'\xd9') or not marker: continue
                size=struct.unpack('>H',stream.read(2))[0]
                data=stream.read(size-2)
                if marker[0] in (0xc0,0xc1,0xc2,0xc3,0xc5,0xc6,0xc7,0xc9,0xca,0xcb,0xcd,0xce,0xcf):
                    h,w=struct.unpack('>HH',data[1:5]); return w,h,'jpeg',False
        raise ValueError('JPEG dimensions not found')
    if len(head)>=12 and head[:4]==b'RIFF' and head[8:12]==b'WEBP':
        with path.open('rb') as stream: data=stream.read(64)
        if data[12:16]==b'VP8X' and len(data)>=30:
            flags=data[20]; w=1+int.from_bytes(data[24:27],'little'); h=1+int.from_bytes(data[27:30],'little')
            return w,h,'webp',bool(flags & 0x10)
    raise ValueError('unsupported or invalid image header; supported formats are PNG, JPEG, and WebP')


def check(artifact, ctx):
    kind=artifact.get('kind'); status=artifact.get('status'); spec=_spec(artifact); results=[]
    if kind in ('concept-2d','reference-2d'):
        if not artifact.get('schema_version') or not isinstance(artifact.get('sources'),list) or not isinstance(artifact.get('authors'),list):
            results.append(Result('art2d-metadata','FAIL',['schema_version, sources, and authors metadata are required']))
        else: results.append(Result('art2d-metadata','PASS'))
        if status in ('verified','released'):
            results.append(Result('art2d-deliverable-state','FAIL',[kind+' is not a production deliverable and cannot be '+status]))
        else: results.append(Result('art2d-deliverable-state','PASS'))
        consumers=[obj.get('id') for _,obj in ctx.artifacts.values() if obj.get('id')!=artifact.get('id') and any((x if isinstance(x,str) else x.get('id'))==artifact.get('id') for x in obj.get('sources',[])+obj.get('upstream',[])) and obj.get('kind') in ('asset-spec-2d','runtime-export-2d')]
        if consumers: results.append(Result('art2d-not-deliverable-source','FAIL',['concept/reference used as production input by '+', '.join(consumers)]))
    if kind not in ('asset-spec-2d','runtime-export-2d'):
        return results
    direction=spec.get('art_direction_id') or artifact.get('art_direction_id')
    refs=ctx.artifacts
    def object_for(value):
        if value not in refs: return None
        pair=refs[value]
        return pair[1] if isinstance(pair,tuple) else pair
    guide=object_for(direction) if direction else None
    if not direction or not guide or guide.get('kind')!='art-direction-2d':
        results.append(Result('art2d-direction','FAIL',['asset must reference an existing art-direction-2d artifact id']))
    else: results.append(Result('art2d-direction','PASS'))
    if kind=='asset-spec-2d':
        exports=[obj for _,obj in refs.values() if obj.get('kind')=='runtime-export-2d' and (obj.get('spec') or {}).get('asset_spec_id')==artifact.get('id')]
        usable=[]; details=[]
        for export in exports:
            checks=check(export,ctx)
            integrity=next((x for x in checks if x.check=='art2d-export-integrity'),None)
            if integrity and integrity.state=='PASS': usable.append(export)
            elif integrity: details.extend(integrity.reasons)
        if not usable: results.append(Result('art2d-runtime-export','FAIL',['asset spec requires at least one existing runtime export with matching metadata']+details))
        else: results.append(Result('art2d-runtime-export','PASS'))
        return results
    path_value=spec.get('file_path') or spec.get('path')
    repo_key=spec.get('repo')
    repo=ctx.registry.get('repos',{}).get(repo_key,{}) if repo_key else {}
    # Repository roots are supplied by the caller's artifact set as optional roots.
    full=ctx.resolve_repo_path(repo_key,path_value) if repo_key and path_value else None
    if not path_value or not repo or not full or not full.is_file():
        reason='registered repository root is unavailable' if repo_key in ctx.registry.get('repos',{}) and repo_key not in ctx.repo_roots else 'runtime export file path/repo is missing, unregistered, unsafe, or does not exist in the registered repo'
        results.append(Result('art2d-export-file','FAIL',[reason]))
        return results
    try:
        w,h,fmt,alpha=_dimensions(full)
        declared=spec.get('dimensions',{})
        mismatch=[]
        if declared.get('width')!=w or declared.get('height')!=h: mismatch.append('declared dimensions do not match image header')
        if str(spec.get('format','')).lower().replace('jpeg','jpg') not in (fmt,fmt.replace('jpeg','jpg')): mismatch.append('declared format does not match image header')
        if bool(spec.get('alpha'))!=alpha: mismatch.append('declared alpha does not match image header')
        expected=spec.get('sha256') or artifact.get('hash')
        actual=hashlib.sha256(full.read_bytes()).hexdigest()
        if not expected or expected.lower()!=actual: mismatch.append('declared SHA-256 is missing or does not match file')
        direction_spec=_spec(guide or {})
        pattern=direction_spec.get('naming_pattern') or r'^[a-z0-9]+_[a-z0-9]+_[a-z0-9]+_[a-z0-9]+$'
        basename=PurePosixPath(str(path_value).replace('\\','/')).stem
        if not re.fullmatch(pattern,basename): mismatch.append('filename does not match art-direction naming convention/default domain_category_name_variant')
        frames=spec.get('animation',{})
        if frames:
            fw=frames.get('frame_width'); fh=frames.get('frame_height'); count=frames.get('frame_count')
            if not all(isinstance(x,int) and x>0 for x in (fw,fh,count)) or w!=fw*count or h!=fh:
                mismatch.append('sprite sheet dimensions must equal frame_count x frame_width by frame_height')
        atlas=spec.get('atlas',{})
        if atlas.get('power_of_two') and (w & (w-1) or h & (h-1)): mismatch.append('atlas requires power-of-two dimensions')
        if atlas.get('max_width') and w>atlas['max_width'] or atlas.get('max_height') and h>atlas['max_height']: mismatch.append('image exceeds declared atlas bounds')
        results.append(Result('art2d-export-integrity','FAIL' if mismatch else 'PASS',mismatch))
    except (OSError,ValueError,struct.error) as exc:
        results.append(Result('art2d-export-integrity','FAIL',[str(exc)]))
    try:
        pillow=ctx.tools('pillow')
    except Exception: pillow=None
    results.append(Result('art2d-palette', 'NOT_AVAILABLE' if not pillow else 'HUMAN_REQUIRED', ['Pillow is unavailable; palette and transparency coverage were not inspected'] if not pillow else ['optional Pillow deep palette inspection is not implemented in this adapter']))
    return results
