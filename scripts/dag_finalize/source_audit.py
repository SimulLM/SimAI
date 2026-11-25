"""Batch Git blob comparison on native Linux; retain raw byte and mode differences."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess


def sha(data):return hashlib.sha256(data).hexdigest()


def compare(source,native):
    listing=subprocess.check_output(['git','-C',str(native),'ls-tree','-rz','HEAD'])
    records=[]
    for item in listing.split(b'\0'):
        if not item:continue
        metadata,name=item.split(b'\t',1);mode,kind,oid=metadata.split()
        if kind!=b'blob':continue
        records.append((mode.decode(),oid.decode(),name.decode()))
    data=subprocess.check_output(['git','-C',str(native),'cat-file','--batch'],input=('\n'.join(r[1] for r in records)+'\n').encode())
    stream=io.BytesIO(data);rows=[]
    for mode,oid,name in records:
        header=stream.readline().split();expected=stream.read(int(header[2]));stream.read(1)
        path=source/name
        if not path.exists() and not path.is_symlink():
            rows.append(dict(path=name,classification='missing',git_blob=oid));continue
        actual=str(path.readlink()).encode() if path.is_symlink() else path.read_bytes()
        classification='byte_match' if actual==expected else 'content_difference'
        if classification!='byte_match' and b'\0' not in expected and b'\0' not in actual:
            try:
                if actual.decode('utf-8').splitlines()==expected.decode('utf-8').splitlines():classification='newline_only'
            except UnicodeDecodeError:pass
        rows.append(dict(path=name,git_blob=oid,git_mode=mode,actual_sha256=sha(actual),git_blob_sha256=sha(expected),
            classification=classification,executable_mode_differs=bool(path.stat().st_mode&0o111)!=(mode=='100755')))
    from collections import Counter
    return dict(counts=dict(Counter(r['classification'] for r in rows)),files=rows,
        substantive=[r['path'] for r in rows if r['classification'] in ('content_difference','missing')],
        note='Raw hashes are preserved. Newline classification is diagnostic only, never reported as byte-clean.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--native',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    results={}
    for name in ('.','SimCCL','aicb','ns-3-alibabacloud'):
        print('Comparing',name,flush=True);results[name]=compare(a.source/name,a.native/name)
    value=dict(repositories=results,status='passed' if all(not results[name]['substantive'] for name in ('SimCCL','aicb','ns-3-alibabacloud')) else 'needs_review',
        root_worktree_changes='Listed against base commit; finalization changes are additionally frozen by source snapshot.')
    a.output.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8');print(json.dumps({k:v['counts'] for k,v in results.items()}))
