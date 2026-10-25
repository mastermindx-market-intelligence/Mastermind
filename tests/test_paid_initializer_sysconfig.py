"""Exact prospective sysconfig alias custody, never target-code execution."""
import contextlib
import errno
import os
from pathlib import Path
import stat
import sys

import pytest
from ops.native_fabric.quota_continuity.candidate import paid_initializer as m
from tests.test_paid_initializer import _preserving_stat_view


@contextlib.contextmanager
def library_fixture(tmp_path,monkeypatch):
    library=tmp_path/'library';library.mkdir(mode=0o700)
    marker=tmp_path/'not-executed';target=library/m._QualifiedSysconfigLink.TARGET
    target.write_text('raise RuntimeError("TARGET_MUST_NOT_EXECUTE")\n');target.chmod(0o644)
    alias=library/m._QualifiedSysconfigLink.NAME;alias.symlink_to(target.name)
    rawopen=os.open;rawstat=os.stat;rawfstat=os.fstat
    directory=rawopen(library,os.O_RDONLY|os.O_DIRECTORY)
    watched={directory:(rawfstat(directory).st_dev,rawfstat(directory).st_ino)}
    try:
        with monkeypatch.context()as model:
            def owned_fstat(fd):
                info=rawfstat(fd)
                return _preserving_stat_view(info,uid=0)if watched.get(fd)==(info.st_dev,info.st_ino)else info
            def owned_stat(name,*args,**kwargs):
                info=rawstat(name,*args,**kwargs)
                if name in (alias.name,target.name)and kwargs.get('dir_fd')==directory and kwargs.get('follow_symlinks')is False:return _preserving_stat_view(info,uid=0)
                return info
            def owned_open(name,flags,*args,**kwargs):
                owned=name in(alias.name,target.name)and kwargs.get('dir_fd')==directory
                if owned:
                    assert flags&os.O_NOFOLLOW
                    if name==alias.name:assert flags&os.O_PATH
                fd=rawopen(name,flags,*args,**kwargs)
                if owned:
                    info=rawfstat(fd);watched[fd]=(info.st_dev,info.st_ino)
                return fd
            model.setattr(os,'open',owned_open);model.setattr(os,'fstat',owned_fstat);model.setattr(os,'stat',owned_stat)
            yield directory,alias,target,marker
    finally:os.close(directory)
    assert not marker.exists()


pytestmark=pytest.mark.skipif(sys.platform!='linux',reason='actual Linux O_PATH/no-follow link and file custody')


def test_actual_exact_link_and_ordinary_target_are_held_without_execution(tmp_path,monkeypatch):
    with library_fixture(tmp_path,monkeypatch)as(directory,alias,target,marker):
        with m._QualifiedSysconfigLink(directory)as node:
            node.check();linkfd=node.fd;targetfd=node.target_fd
            assert os.readlink(alias)==target.name
            assert stat.S_ISLNK(os.fstat(linkfd).st_mode)and stat.S_ISREG(os.fstat(targetfd).st_mode)
        for fd in(linkfd,targetfd):
            with pytest.raises(OSError)as error:os.fstat(fd)
            assert error.value.errno==errno.EBADF
        assert not marker.exists()


@pytest.mark.parametrize('destination',['../escape.py','/outside.py','other.py','sub/target.py','./_sysconfigdata__x86_64-linux-gnu.py'])
def test_retarget_escape_and_other_relative_shapes_refuse_before_target_read(tmp_path,monkeypatch,destination):
    with library_fixture(tmp_path,monkeypatch)as(directory,alias,target,marker):
        alias.unlink();alias.symlink_to(destination);rawpread=os.pread;reads=[]
        def read(fd,*args):reads.append(fd);return rawpread(fd,*args)
        with monkeypatch.context()as fault:
            fault.setattr(os,'pread',read)
            with pytest.raises(m.InitializerCommitmentRefused):m._QualifiedSysconfigLink(directory)
        assert not reads and not marker.exists()


@pytest.mark.parametrize('fault',['chain','writable','multiple_links','extended_acl','foreign_uid'])
def test_target_chain_custody_mode_and_acl_refuse(tmp_path,monkeypatch,fault):
    with library_fixture(tmp_path,monkeypatch)as(directory,alias,target,marker):
        if fault=='chain':
            other=target.with_name('other.py');other.write_bytes(b'inert');target.unlink();target.symlink_to(other.name)
        elif fault=='writable':target.chmod(0o664)
        elif fault=='multiple_links':os.link(target,target.with_name('second.py'))
        original=os.getxattr;original_fstat=os.fstat
        def foreign(fd):
            info=original_fstat(fd)
            return _preserving_stat_view(info,uid=1)if stat.S_ISREG(info.st_mode)else info
        def acl(fd,key,*args,**kwargs):
            if type(fd)is int and stat.S_ISREG(os.fstat(fd).st_mode):return b'inert-acl'
            return original(fd,key,*args,**kwargs)
        with monkeypatch.context()as patch:
            if fault=='extended_acl':patch.setattr(os,'getxattr',acl)
            if fault=='foreign_uid':patch.setattr(os,'fstat',foreign)
            with pytest.raises((m.InitializerCommitmentRefused,OSError)):m._QualifiedSysconfigLink(directory)
        assert not marker.exists()


@pytest.mark.parametrize('fault',['retarget','replacement','content'])
def test_late_namespace_and_content_change_refuse_and_dispose(tmp_path,monkeypatch,fault):
    with library_fixture(tmp_path,monkeypatch)as(directory,alias,target,marker):
        node=m._QualifiedSysconfigLink(directory);fd=node.target_fd;linkfd=node.fd
        with pytest.raises(m.InitializerCommitmentRefused):
            with node:
                if fault=='retarget':alias.unlink();alias.symlink_to('other.py')
                elif fault=='replacement':target.unlink();target.write_bytes(b'changed')
                else:target.write_bytes(b'changed')
                node.check()
        for owned in(fd,linkfd):
            with pytest.raises(OSError):os.fstat(owned)


def test_actual_content_hash_refuses_even_with_modelled_stable_metadata(tmp_path,monkeypatch):
    with library_fixture(tmp_path,monkeypatch)as(directory,alias,target,marker):
        node=m._QualifiedSysconfigLink(directory);before=os.fstat(node.target_fd)
        rawfstat=os.fstat;rawstat=os.stat
        def stable_fstat(fd):return before if fd==node.target_fd else rawfstat(fd)
        def stable_stat(name,*args,**kwargs):
            if name==target.name and kwargs.get('dir_fd')==directory:return before
            return rawstat(name,*args,**kwargs)
        with pytest.raises(m.InitializerCommitmentRefused):
            with monkeypatch.context()as patch:
                patch.setattr(os,'fstat',stable_fstat);patch.setattr(os,'stat',stable_stat)
                with node:
                    target.write_bytes(b'x'*before.st_size);node.check()
