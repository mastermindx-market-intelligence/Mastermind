"""Actual composed browser check, controlled source events and auth fixtures."""
import asyncio, hashlib, json
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric import rsa
from playwright.sync_api import sync_playwright

# Verification requires Playwright/Chromium and PyJWT. Neither is installed here.
ROOT=Path(__file__).resolve().parents[1]
from integrations.mastermind_window_reader.recorded_view import render_connection_shell
from tests.mastermind_window_reader.test_window_resource import signed_window
from tests.mastermind_window_reader.test_read_resource import request
from tests.mastermind_window_reader.test_existing_auth_composition import token
from tests.mastermind_window_reader.test_live_window import REF,KEY

def main():
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    app,state,source=signed_window(key);signed=token(key)
    calls=[]
    async def read():
        status,headers,body=await request(app,headers=[(b'host',b'workspace.example'),(b'authorization',('Bearer '+signed).encode())])
        calls.append({'status':status,'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest()})
        return {'status':status,'body':json.loads(body)}
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
        page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];requests=[]
        page.on('pageerror',lambda e:errors.append(str(e)));page.on('request',lambda r:requests.append(r.url))
        page.expose_function('fixtureRead',read)
        page.set_content(render_connection_shell())
        page.evaluate("ref=>window.MastermindReadConnection.attach({expectedLane:ref,sourceKind:'live-window',read:()=>window.fixtureRead()})",REF)
        source.publish('a','Synthetic fixture: partial response delivered to the existing projection. The source turn is still nonterminal.')
        assert page.evaluate('window.MastermindReadConnection.refresh()')
        before=page.locator('.message-text').inner_text();assert 'nonterminal' in before
        source.publish('b','Synthetic fixture: a second response is available. It must survive the first response being corrected.',position=2)
        source.publish('a','Synthetic fixture: completed replacement. The earlier draft is replaced in place, not duplicated.\n\nThis demonstrates the reader connection only. No provider was invoked and no work was accepted.','completed')
        assert page.evaluate('window.MastermindReadConnection.refresh()');page.locator('#compare').click()
        assert page.locator('.message-text').count()==2
        page.locator('#capture-notice').evaluate("e=>e.textContent='TEST FIXTURE · NO PROVIDER CONNECTED'")
        page.screenshot(path=str(ROOT/'tests/mastermind_window_reader/window-connected.png'),full_page=True)
        source.owner.publish(KEY,method='item/updated',params={'item':{'type':'agentMessage','id':'bad'}},native_turn_id=KEY.native_turn_id)
        assert page.evaluate('window.MastermindReadConnection.refresh()')
        assert 'gap' in page.locator('#window-state').inner_text()
        page.locator('#evidence').click()
        page.locator('#capture-notice').evaluate("e=>e.textContent='TEST FIXTURE · NO PROVIDER CONNECTED'")
        page.screenshot(path=str(ROOT/'tests/mastermind_window_reader/window-evidence.png'),full_page=True)
        source.owner.revoke_grant(source.grant)
        assert page.evaluate('window.MastermindReadConnection.refresh()') is False
        assert page.locator('.message-text').count()==0
        page.screenshot(path=str(ROOT/'tests/mastermind_window_reader/window-revoked.png'),full_page=True)
        report=dict(result='PASS',scope='consumer integration with synthetic source events and permission/key fixtures',
          upstream_blob='77a23ad9eeb5f49660beb6a8a0a63c5a5a88065f',browser_version=browser.version,
          nonterminal_response_observed=True,final_replacement_observed=True,second_item_preserved=True,
          gap_disclosed=True,revocation_cleared_content=True,script_errors=errors,resource_requests=requests,
          source_read_responses=calls,provider_invocations=0,installed_proof=False,public_origin_tested=False,
          note='HTML supplied at about:blank under existing browser policy. In-process host binding invokes real ASGI and RS256 verifier.')
        assert not errors and not requests
        (ROOT/'tests/mastermind_window_reader/WINDOW_BROWSER_PROOF.json').write_text(json.dumps(report,indent=2))
        print(json.dumps({k:report[k] for k in ['result','nonterminal_response_observed','final_replacement_observed','gap_disclosed','revocation_cleared_content','provider_invocations']}))
        browser.close()
if __name__=='__main__':main()
