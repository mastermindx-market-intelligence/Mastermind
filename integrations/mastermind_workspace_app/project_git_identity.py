"""Root-sealed service Git/GitHub identity for the existing fixed publisher.

Source action membership never chooses or authenticates this credential. The
normal installed Control configuration explicitly selects this independent
service identity. This owner only reloads that sealed selection, checks the
currently provisioned GitHub identity and implements fixed PR lookup/create;
it never reads or returns a token, installs credentials, merges or selects data.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import urlencode

from control_plane.workspace_project_git_publisher import (
    PublisherBinding, REPOSITORY, PrLookupAmbiguous, PrLookupForeign,
    PrOwnerUnknownOutcome, _valid_branch_name,
)

_SCHEMA = 'mastermind.workspace_source_publisher.v1'
_ORIGIN = 'https://github.com/' + REPOSITORY + '.git'
_FIELDS = {'schema','worktree','default_branch','github_login','gh_binary','gh_sha256','source_author_receipt_sha256'}


def _fail():
    raise ValueError('SOURCE_PUBLISHER_UNAVAILABLE')


def validate_publisher_selection(value):
    """Pure closed config validation. This does not issue an identity owner."""
    if (type(value) is not dict or set(value) != _FIELDS or value.get('schema') != _SCHEMA
            or type(value['worktree']) is not str or not Path(value['worktree']).is_absolute()
            or not _valid_branch_name(value['default_branch'])
            or type(value['github_login']) is not str
            or re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})',value['github_login']) is None
            or type(value['gh_binary']) is not str or not Path(value['gh_binary']).is_absolute()
            or any(type(value[k]) is not str or re.fullmatch(r'[0-9a-f]{64}',value[k]) is None
                   for k in ('gh_sha256','source_author_receipt_sha256'))):
        _fail()
    return dict(value)


def _git_environment():
    env=dict(os.environ)
    for key in tuple(env):
        if key in {"GIT_DIR","GIT_COMMON_DIR","GIT_WORK_TREE","GIT_INDEX_FILE","GIT_OBJECT_DIRECTORY",
                   "GIT_ALTERNATE_OBJECT_DIRECTORIES","GIT_NAMESPACE","GIT_SHALLOW_FILE",
                   "GIT_CONFIG_COUNT","GIT_CONFIG_PARAMETERS"} or key.startswith(("GIT_CONFIG_KEY_","GIT_CONFIG_VALUE_")):
            env.pop(key,None)
    env['GIT_NO_REPLACE_OBJECTS']='1'
    env['GIT_TERMINAL_PROMPT']='0'
    return env


class InstalledProjectGitIdentity:
    """Fixed real process composition; callers cannot inject a PR handler."""
    def __init__(self, *, config_path, expected_config_sha256):
        self._path = Path(config_path)
        if (type(expected_config_sha256) is not str
                or re.fullmatch(r'[0-9a-f]{64}',expected_config_sha256) is None):_fail()
        self._expected = expected_config_sha256
        raw = self._configuration()
        self._selection = validate_publisher_selection(raw['workspace_source_publication'])
        self.binding = PublisherBinding(worktree=self._selection['worktree'],expected_origin=_ORIGIN,
            default_branch=self._selection['default_branch'],
            publisher_identity=hashlib.sha256(json.dumps(self._selection,sort_keys=True,separators=(',',':')).encode()).hexdigest())

    def _configuration(self):
        from ops.executive_os.executive_mcp_entry import require_sealed_path
        require_sealed_path(self._path)
        before=self._path.stat(); data=self._path.read_bytes(); after=self._path.stat()
        if (len(data)>262144 or hashlib.sha256(data).hexdigest()!=self._expected
                or (before.st_dev,before.st_ino,before.st_mtime_ns,before.st_size)!=(after.st_dev,after.st_ino,after.st_mtime_ns,after.st_size)):_fail()
        def unique(pairs):
            out={}
            for key,value in pairs:
                if key in out:_fail()
                out[key]=value
            return out
        result=json.loads(data,object_pairs_hook=unique)
        if type(result) is not dict:_fail()
        return result

    def _current(self):
        from ops.executive_os.executive_mcp_entry import require_sealed_path
        selected=validate_publisher_selection(self._configuration()['workspace_source_publication'])
        if selected!=self._selection:_fail()
        executable=Path(selected['gh_binary'])
        require_sealed_path(executable)
        if (not os.access(executable,os.X_OK) or not 0 < executable.stat().st_size <= 67108864
                or hashlib.sha256(executable.read_bytes()).hexdigest()!=selected['gh_sha256']):_fail()
        if (os.environ.get('GH_HOST','github.com')!='github.com'
                or any(key in os.environ for key in ('GIT_SSL_NO_VERIFY','GIT_SSL_CAINFO','GIT_SSL_CAPATH','GIT_PROXY_COMMAND'))):_fail()
        return selected

    def _process(self,argv,*,payload=None,limit=262144):
        # Secret-bearing stderr is never returned or included in exceptions.
        from control_plane.ceo_boot_packet import bounded_subprocess_runner
        try:
            result=bounded_subprocess_runner(argv,cwd=Path(self.binding.worktree),input_bytes=payload,
                timeout=15,max_bytes=limit,env=_git_environment())
        except Exception:_fail()
        if (type(result) is not dict or result.get('code')!=0 or type(result.get('stdout')) is not str
                or any(result.get(key) is True for key in ('timed_out','limit_exceeded','invalid_utf8'))):_fail()
        return result['stdout'].encode('utf-8')

    def qualify(self,binding):
        try:
            selected=self._current()
            if binding!=self.binding or Path(binding.worktree).is_symlink():return False
            gh=selected['gh_binary']
            # Git and the PR API must use the same explicitly selected existing
            # gh account; no Auth0→GitHub credential mapping is performed.
            helper=self._process(['/usr/bin/git','--no-replace-objects','config','--get-urlmatch','credential.helper',_ORIGIN],limit=4096).decode().strip()
            if helper not in {'!'+gh+' auth git-credential','!'+gh.replace(' ','\\ ')+' auth git-credential'}:return False
            if self._has_unsafe_git_config():return False
            login=self._process([gh,'api','--hostname','github.com','user','--jq','.login'],limit=256).decode().strip()
            if login!=selected['github_login']:return False
            self._current()
            return True
        except (ValueError,KeyError,TypeError,OSError,UnicodeError):return False

    def _has_unsafe_git_config(self):
        # `git config --get-regexp` exits1 on absence; keep that distinct from
        # invocation failure without printing values or credential headers.
        try:
            result=subprocess.run(['/usr/bin/git','--no-replace-objects','config','--name-only','--get-regexp',r'^(http\..*\.(extraheader|proxy|sslverify|sslcainfo|sslcapath)|http\.(extraheader|proxy|sslverify|sslcainfo|sslcapath)|url\..*\.(insteadof|pushinsteadof))$'],
                cwd=self.binding.worktree,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=5,env=_git_environment())
        except (OSError,subprocess.SubprocessError):_fail()
        if result.returncode not in {0,1}:_fail()
        return result.returncode==0 or bool(result.stdout)

    def _api(self,path,*,payload=None):
        selected=self._current()
        if not self.qualify(self.binding):_fail()
        argv=[selected['gh_binary'],'api','--hostname','github.com',path]
        if payload is not None:argv+=['--method','POST','--input','-']
        raw=self._process(argv,payload=None if payload is None else json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode())
        result=json.loads(raw)
        if not self.qualify(self.binding):_fail()
        return result

    def _receipt(self,item,branch,digest):
        marker='Mastermind source operation SHA256: '+digest
        if (type(item) is not dict or type(item.get('number')) is not int or item['number']<=0
                or item.get('html_url')!='https://github.com/'+REPOSITORY+'/pull/'+str(item['number'])
                or type(item.get('body')) is not str or marker not in item['body'].splitlines()
                or item.get('head',{}).get('ref')!=branch
                or item.get('head',{}).get('repo',{}).get('full_name')!=REPOSITORY
                or item.get('base',{}).get('ref')!=self.binding.default_branch
                or item.get('base',{}).get('repo',{}).get('full_name')!=REPOSITORY
                or type(item.get('head',{}).get('sha')) is not str
                or re.fullmatch(r'[0-9a-f]{40}',item['head']['sha']) is None):raise PrLookupForeign()
        return {'number':item['number'],'url':item['html_url'],'head_branch':branch,'head_commit':item['head']['sha']}

    def find(self,binding,branch,request_sha256):
        if binding!=self.binding or not _valid_branch_name(branch) or re.fullmatch(r'[0-9a-f]{64}',request_sha256) is None:raise PrLookupForeign()
        try:
            path='repos/'+REPOSITORY+'/pulls?'+urlencode({'state':'all','head':REPOSITORY.split('/')[0]+':'+branch,'base':binding.default_branch,'per_page':2})
            rows=self._api(path)
            if type(rows) is not list or len(rows)>1:raise PrLookupAmbiguous()
            return None if not rows else self._receipt(rows[0],branch,request_sha256)
        except (ValueError,KeyError,TypeError,OSError):raise PrLookupAmbiguous() from None

    def create(self,binding,branch,expected_commit,request_sha256):
        if binding!=self.binding or not _valid_branch_name(branch) or re.fullmatch(r'[0-9a-f]{40}',expected_commit) is None or re.fullmatch(r'[0-9a-f]{64}',request_sha256) is None:raise PrLookupForeign()
        try:
            item=self._api('repos/'+REPOSITORY+'/pulls',payload={'head':branch,'base':binding.default_branch,
                'title':'Project source update','body':'Mastermind source operation SHA256: '+request_sha256+'\nExpected canonical source: '+expected_commit+'\n\nSource proposal; canonical landing remains protected.'})
            return self._receipt(item,branch,request_sha256)
        except (ValueError,KeyError,TypeError,OSError):raise PrOwnerUnknownOutcome() from None
