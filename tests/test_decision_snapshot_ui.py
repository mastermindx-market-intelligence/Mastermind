"""Inspector source contract; HTTP/browser behavior has separate integration proof."""
from pathlib import Path
from html.parser import HTMLParser

ROOT=Path(__file__).resolve().parents[1]


class Page(HTMLParser):
    def __init__(self):
        super().__init__();self.ids=set();self.attrs=[];self.scripts=[]
    def handle_starttag(self, tag, attrs):
        d=dict(attrs);self.attrs.append(d)
        if 'id' in d:self.ids.add(d['id'])
        if tag=='script':self.scripts.append(d)


def test_inspector_shell_has_state_navigation_and_accessible_controls():
    p=ROOT/'app/static/decision-evidence.html'
    assert p.is_file(), 'missing inspector shell'
    page=Page();page.feed(p.read_text())
    assert {'status','refresh','snapshot-select','domain-list','rows','gaps','next-page','previous-page','theme-toggle'} <= page.ids
    assert all(not any(k.startswith('on') for k in a) for a in page.attrs)
    assert page.scripts and all(s.get('src')=='/decision-evidence.js' for s in page.scripts)
    assert any(a.get('aria-live')=='polite' for a in page.attrs)


def test_browser_code_has_no_credential_store_or_mutating_request():
    p=ROOT/'app/static/decision-evidence.js'
    assert p.is_file(), 'missing inspector script'
    text=p.read_text()
    for forbidden in ['innerHTML','outerHTML','insertAdjacentHTML','eval(', 'localStorage', 'sessionStorage', 'Bearer ', 'method: "POST"']:
        assert forbidden not in text
    assert 'AbortController' in text and 'textContent' in text
    assert 'snapshot_id' in text and 'next_offset' in text
