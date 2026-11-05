"""Request-local DATA materialization under the actual canonical observation.

The installed collector retains its original executable/config root and seal.
Only a nominal, still-current publisher-issued view can supply this temporary
Git DATA root. Nothing changes the configured clone/HEAD or persists a view.
The fixed child receives CODE and DATA coordinates separately; the DATA path
and commit are observations, never a serialized permission receipt.
"""
from contextlib import contextmanager
import os
from pathlib import Path
import re
import tempfile
import time


@contextmanager
def materialized_project_data(view, *, pinned_macro_root, deadline):
    from control_plane.project_canonical_data import CanonicalProjectDataView
    if type(view) is not CanonicalProjectDataView:
        raise ValueError('CANONICAL_DATA_UNAVAILABLE')
    # Only this pure materialization + fixed child acquisition is coalesced.
    # The owner keeps full current source/default/Event/auth checks around the
    # logical response and caps this operation at both original and child
    # deadlines. It is never a publication or human-Review scope.
    with view.capture_scope(deadline=deadline) as capture:
        with _materialized_project_data(view,pinned_macro_root=pinned_macro_root,
                deadline=deadline,operation=capture.operation) as pair:
            yield pair


@contextmanager
def _materialized_project_data(view, *, pinned_macro_root, deadline, operation):
    from control_plane.project_canonical_data import CanonicalProjectDataView
    from integrations.executive_mcp.installed import (
        _MacroMaterializationPlan, _macro_brief_content_paths, _tree_directory_paths,
        _direct_git_directory, _clone_git_read_database, _check_deadline,
    )
    if (type(view) is not CanonicalProjectDataView
            or view._code_root != Path(pinned_macro_root).resolve()):
        raise ValueError('CANONICAL_DATA_UNAVAILABLE')
    view.check()
    publisher=view._owner.publisher
    def git(args,**kwargs):
        _check_deadline(deadline,label='canonical DATA materialization')
        view.check()
        result=publisher._git(args,operation,**kwargs)
        if result.returncode!=0:raise ValueError('CANONICAL_DATA_UNAVAILABLE')
        return result.stdout
    raw=git(['ls-tree','-r','-z',view.data_commit])
    if len(raw)>16777216:raise ValueError('CANONICAL_DATA_UNAVAILABLE')
    objects={}
    for item in raw.split(b'\0'):
        if not item:continue
        header,path=item.split(b'\t',1)
        mode,kind,oid=header.split(b' ')
        name=path.decode('utf-8')
        if name in objects:raise ValueError('CANONICAL_DATA_UNAVAILABLE')
        objects[name]=(mode.decode('ascii'),kind,oid.decode('ascii'))
    paths=_macro_brief_content_paths(set(objects))
    if not paths or len(paths)>16384:raise ValueError('CANONICAL_DATA_UNAVAILABLE')
    selected={path:objects[path] for path in paths}
    if any(mode!='100644' or kind!=b'blob' or re.fullmatch(r'[0-9a-f]{40}',oid) is None
           for mode,kind,oid in selected.values()):raise ValueError('CANONICAL_DATA_UNAVAILABLE')
    ids=sorted({oid for _,_,oid in selected.values()})
    batch=git(['cat-file','--batch'],stdin_bytes=('\n'.join(ids)+'\n').encode('ascii'))
    if len(batch)>33554432:raise ValueError('CANONICAL_DATA_UNAVAILABLE')
    offset=0;blobs={}
    for expected in ids:
        end=batch.index(b'\n',offset)
        oid,kind,size=batch[offset:end].split(b' ')
        if oid.decode('ascii')!=expected or kind!=b'blob' or not size.isdigit():raise ValueError('CANONICAL_DATA_UNAVAILABLE')
        length=int(size);start=end+1;finish=start+length
        if length>1048576 or batch[finish:finish+1]!=b'\n':raise ValueError('CANONICAL_DATA_UNAVAILABLE')
        value=batch[start:finish]
        import hashlib
        if hashlib.sha1(b'blob '+str(length).encode()+b'\0'+value).hexdigest()!=expected:raise ValueError('CANONICAL_DATA_UNAVAILABLE')
        blobs[expected]=value;offset=finish+1
    if offset!=len(batch):raise ValueError('CANONICAL_DATA_UNAVAILABLE')
    metadata=_direct_git_directory(view._root,label='canonical DATA publisher')
    if metadata is None:raise ValueError('CANONICAL_DATA_UNAVAILABLE')
    plan=_MacroMaterializationPlan(view.data_commit,frozenset(paths),frozenset(_tree_directory_paths(paths)),
        {path:(selected[path][0],selected[path][2]) for path in paths})
    with tempfile.TemporaryDirectory(prefix='mmx-canonical-data-') as temporary:
        root=Path(temporary).resolve()/'macro';root.mkdir(mode=0o700)
        _clone_git_read_database(metadata,root/'.git',deadline=deadline)
        # This is a new private materialization only. The configured source and
        # publisher clones keep their original HEAD, index and worktree bytes.
        (root/'.git'/'HEAD').write_text(view.data_commit+'\n',encoding='ascii')
        for rel in sorted(plan.directories,key=lambda item:(len(item.split('/')),item)):
            (root/rel).mkdir(mode=0o700)
        for rel in sorted(paths):
            _check_deadline(deadline,label='canonical DATA materialization')
            (root/rel).write_bytes(blobs[selected[rel][2]])
            (root/rel).chmod(0o600)
        view.check()
        yield root,plan
        view.check()
