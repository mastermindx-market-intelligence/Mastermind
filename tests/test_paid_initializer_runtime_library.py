"""Finite library-chain mechanics; owned metadata premise, never a loader."""
import contextlib
import errno
import os
import stat
import sys

import pytest
from ops.native_fabric.quota_continuity.candidate import paid_initializer as m
from tests.test_paid_initializer import _preserving_stat_view

pytestmark=pytest.mark.skipif(sys.platform!='linux',reason='real Linux linkFD/ACL/held library mechanics')


@contextlib.contextmanager
def library_chain(tmp_path,monkeypatch):
    base=tmp_path/'usr/lib';config=base/'python3.12/config-3.12-x86_64-linux-gnu';runtime=base/'x86_64-linux-gnu'
    config.mkdir(parents=True);runtime.mkdir()
    first=config/m._QualifiedRuntimeLibrary.NAME;second=runtime/m._RuntimeSonameLink.NAME;target=runtime/m._QualifiedRuntimeLibrary.TARGET
    first.symlink_to(m._QualifiedRuntimeLibrary.LINK_VALUE);second.symlink_to(target.name)
    target.write_bytes(b'\x7fELF'+b'inert-not-executed'*32);target.chmod(0o644)
    rawopen=os.open;rawfstat=os.fstat;rawstat=os.stat
    a=rawopen(config,os.O_RDONLY|os.O_DIRECTORY);b=rawopen(runtime,os.O_RDONLY|os.O_DIRECTORY)
    watched={fd:(rawfstat(fd).st_dev,rawfstat(fd).st_ino)for fd in(a,b)}
    try:
        with monkeypatch.context()as patch:
            def owned_fstat(fd):
                info=rawfstat(fd)
                return _preserving_stat_view(info,uid=0)if watched.get(fd)==(info.st_dev,info.st_ino)else info
            def owned_stat(name,*args,**kwargs):
                info=rawstat(name,*args,**kwargs)
                if kwargs.get('dir_fd')in(a,b)and kwargs.get('follow_symlinks')is False:return _preserving_stat_view(info,uid=0)
                return info
            def owned_open(name,flags,*args,**kwargs):
                owned=kwargs.get('dir_fd')in(a,b)
                if owned:
                    assert flags&os.O_NOFOLLOW
                    if name in(first.name,second.name):assert flags&os.O_PATH
                fd=rawopen(name,flags,*args,**kwargs)
                if owned:
                    info=rawfstat(fd);watched[fd]=(info.st_dev,info.st_ino)
                return fd
            patch.setattr(os,'fstat',owned_fstat);patch.setattr(os,'stat',owned_stat);patch.setattr(os,'open',owned_open)
            yield a,b,first,second,target
    finally:os.close(b);os.close(a)


def test_actual_two_fixed_links_and_ordinary_library_are_held_and_closed(tmp_path,monkeypatch):
    with library_chain(tmp_path,monkeypatch)as(a,b,first,second,target):
        with m._QualifiedRuntimeLibrary(a,b)as node:
            node.check();fds=(node.fd,node.soname.fd,node.target_fd)
            assert all(stat.S_ISLNK(os.fstat(fd).st_mode)for fd in fds[:2])
            assert stat.S_ISREG(os.fstat(fds[2]).st_mode)
            assert node.LIMIT==16777216 and m._QualifiedSysconfigLink.LIMIT==1048576
        for fd in fds:
            with pytest.raises(OSError)as error:os.fstat(fd)
            assert error.value.errno==errno.EBADF


@pytest.mark.parametrize('hop,payload',[(0,'/outside'),(0,'../../other/library.so'),(0,'./../../x86_64-linux-gnu/libpython3.12.so.1'),(1,'../other.so'),(1,'/usr/lib/other.so'),(1,'libpython3.12.so.1.0.extra')])
def test_either_link_nonliteral_or_escape_refuses_before_content(tmp_path,monkeypatch,hop,payload):
    with library_chain(tmp_path,monkeypatch)as(a,b,first,second,target):
        link=(first,second)[hop];link.unlink();link.symlink_to(payload);reads=[];original=os.pread
        def read(fd,*args):reads.append(fd);return original(fd,*args)
        with monkeypatch.context()as patch:
            patch.setattr(os,'pread',read)
            with pytest.raises(m.InitializerCommitmentRefused):m._QualifiedRuntimeLibrary(a,b)
        assert not reads


@pytest.mark.parametrize('fault',['chain','writable_target','foreign_target','multiple_links','oversize','acl','writable_config','writable_runtime'])
def test_library_target_and_ancestor_guards_remain_closed(tmp_path,monkeypatch,fault):
    with library_chain(tmp_path,monkeypatch)as(a,b,first,second,target):
        if fault=='chain':target.unlink();target.symlink_to('another.so')
        elif fault=='writable_target':target.chmod(0o666)
        elif fault=='multiple_links':os.link(target,target.with_name('hardlink'))
        elif fault=='oversize':
            with target.open('wb')as file:file.truncate(16777217)
        elif fault=='writable_config':first.parent.chmod(0o777)
        elif fault=='writable_runtime':target.parent.chmod(0o777)
        fstat=os.fstat;getxattr=os.getxattr
        def foreign(fd):
            info=fstat(fd)
            return _preserving_stat_view(info,uid=1)if stat.S_ISREG(info.st_mode)else info
        def acl(fd,key,*args,**kwargs):
            if type(fd)is int and stat.S_ISREG(fstat(fd).st_mode):return b'inert-acl'
            return getxattr(fd,key,*args,**kwargs)
        with monkeypatch.context()as patch:
            if fault=='foreign_target':patch.setattr(os,'fstat',foreign)
            if fault=='acl':patch.setattr(os,'getxattr',acl)
            with pytest.raises((m.InitializerCommitmentRefused,OSError)):m._QualifiedRuntimeLibrary(a,b)


@pytest.mark.parametrize('fault',['first','second','replacement','content'])
def test_late_either_link_or_library_change_refuses_and_closes(tmp_path,monkeypatch,fault):
    with library_chain(tmp_path,monkeypatch)as(a,b,first,second,target):
        node=m._QualifiedRuntimeLibrary(a,b);fds=(node.fd,node.soname.fd,node.target_fd)
        with pytest.raises(m.InitializerCommitmentRefused):
            with node:
                if fault in('first','second'):
                    link=first if fault=='first'else second;link.unlink();link.symlink_to('different.so')
                elif fault=='replacement':target.unlink();target.write_bytes(b'new')
                else:target.write_bytes(b'changed')
                node.check()
        for fd in fds:
            with pytest.raises(OSError):os.fstat(fd)


def test_library_hash_refuses_real_byte_change_with_stable_modelled_stat(tmp_path,monkeypatch):
    with library_chain(tmp_path,monkeypatch)as(a,b,first,second,target):
        node=m._QualifiedRuntimeLibrary(a,b);before=os.fstat(node.target_fd);fstat=os.fstat;named=os.stat
        def stable(fd):return before if fd==node.target_fd else fstat(fd)
        def stable_name(name,*args,**kwargs):
            if name==target.name and kwargs.get('dir_fd')==b:return before
            return named(name,*args,**kwargs)
        with pytest.raises(m.InitializerCommitmentRefused):
            with monkeypatch.context()as patch:
                patch.setattr(os,'fstat',stable);patch.setattr(os,'stat',stable_name)
                with node:
                    target.write_bytes(b'x'*before.st_size);node.check()
