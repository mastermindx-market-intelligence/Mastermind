from dataclasses import replace
import pytest

from integrations.mastermind_browser_devtools.contract import (
    ALLOWED_BACKEND_TOOLS,
    DEVTOOLS_MCP_VERSION,
    BackendContractError,
    BackendToolCall,
    build_auto_connect_plan,
    project_backend_call,
    attest_backend_catalog,
)

NODE='/Users/test/.local/node/bin/node'
CLI='/opt/mmx/node_modules/chrome-devtools-mcp/build/src/bin/chrome-devtools-mcp.js'
PROFILE='/Users/test/Library/Application Support/Google/Chrome'
DIGEST='a'*64


def plan():
    return build_auto_connect_plan(
        node_executable=NODE,
        cli_path=CLI,
        user_data_dir=PROFILE,
        installed_version=DEVTOOLS_MCP_VERSION,
        observed_tool_schema_digest=DIGEST,
    )


def test_plan_is_private_existing_browser_attachment_not_a_launcher():
    p=plan()
    assert p.command == NODE
    assert p.backend_version == '1.10.1'
    assert p.observed_tool_schema_digest == DIGEST
    assert p.attachment_mode == 'existing_chrome_autoconnect'
    assert p.requires_browser_user_consent is True
    assert p.page_id_routing is True
    assert p.is_admission is False
    args=set(p.argv)
    assert '--autoConnect' in args
    assert '--pageIdRouting' in args
    assert f'--userDataDir={PROFILE}' in args
    assert '--no-usage-statistics' in args
    assert '--no-performance-crux' in args
    assert '--no-category-performance' in args
    assert '--no-category-network' in args
    assert '--no-category-memory' in args
    assert '--no-category-emulation' in args
    assert '--no-javascript-evaluation' in args
    assert '--screenshot-format=jpeg' in args
    assert '--screenshot-quality=70' in args
    assert '--screenshot-max-width=1600' in args
    assert '--screenshot-max-height=1200' in args
    assert not any('load-extension' in x for x in args)
    assert not any('remote-debugging-port' in x for x in args)
    assert p.allowed_backend_tools == ALLOWED_BACKEND_TOOLS


def test_backend_version_and_catalog_digest_are_pinned():
    with pytest.raises(BackendContractError):
        build_auto_connect_plan(
            node_executable=NODE, cli_path=CLI, user_data_dir=PROFILE,
            installed_version='1.10.2', observed_tool_schema_digest=DIGEST)
    for digest in ['', 'A'*64, '0'*63, '/tmp/catalog']:
        with pytest.raises(BackendContractError):
            build_auto_connect_plan(
                node_executable=NODE, cli_path=CLI, user_data_dir=PROFILE,
                installed_version=DEVTOOLS_MCP_VERSION,
                observed_tool_schema_digest=digest)


@pytest.mark.parametrize('field,value', [
    ('node_executable','node'),
    ('node_executable','/tmp/../bin/node'),
    ('cli_path','/tmp/server.js'),
    ('user_data_dir','relative/profile'),
    ('user_data_dir','/tmp/../profile'),
])
def test_controller_owned_paths_must_be_absolute_normalized(field,value):
    kwargs=dict(node_executable=NODE,cli_path=CLI,user_data_dir=PROFILE,
                installed_version=DEVTOOLS_MCP_VERSION,
                observed_tool_schema_digest=DIGEST)
    kwargs[field]=value
    with pytest.raises(BackendContractError):
        build_auto_connect_plan(**kwargs)


def test_closed_tool_surface_does_not_expose_general_debugging_or_file_actions():
    assert ALLOWED_BACKEND_TOOLS == frozenset({
        'list_pages','take_snapshot','take_screenshot','wait_for',
        'click','fill','type_text','press_key','navigate_page',
    })
    for forbidden in {
        'evaluate_script','upload_file','new_page','close_page','select_page',
        'list_network_requests','get_network_request','lighthouse_audit',
        'install_extension','drag','hover','fill_form','emulate','resize_page',
    }:
        assert forbidden not in ALLOWED_BACKEND_TOOLS


def test_list_pages_is_the_only_call_without_page_id():
    assert project_backend_call('list_pages', page_id=None, arguments={}) == BackendToolCall(
        tool_name='list_pages', arguments={})
    for name in ALLOWED_BACKEND_TOOLS-{'list_pages'}:
        with pytest.raises(BackendContractError):
            project_backend_call(name,page_id=None,arguments={})


@pytest.mark.parametrize('value',[0,-1,True,1.5,'1'])
def test_page_id_must_be_positive_integer(value):
    with pytest.raises(BackendContractError):
        project_backend_call('take_snapshot',page_id=value,arguments={})


def test_snapshot_and_screenshot_strip_file_output_and_control_size():
    assert project_backend_call('take_snapshot',page_id=7,arguments={'verbose':False}) == BackendToolCall(
        tool_name='take_snapshot',arguments={'pageId':7,'verbose':False})
    assert project_backend_call('take_screenshot',page_id=7,arguments={}) == BackendToolCall(
        tool_name='take_screenshot',arguments={'pageId':7,'format':'jpeg','quality':70,'fullPage':False})
    for tool,args in [
        ('take_snapshot',{'filePath':'/tmp/x'}),
        ('take_screenshot',{'filePath':'/tmp/x'}),
        ('take_screenshot',{'fullPage':True}),
        ('take_screenshot',{'format':'png'}),
    ]:
        with pytest.raises(BackendContractError):
            project_backend_call(tool,page_id=7,arguments=args)


def test_click_and_fill_require_snapshot_uid_and_bound_values():
    assert project_backend_call('click',page_id=3,arguments={'uid':'1_5'}) == BackendToolCall(
        tool_name='click',arguments={'pageId':3,'uid':'1_5','dblClick':False,'includeSnapshot':False})
    assert project_backend_call('fill',page_id=3,arguments={'uid':'1_6','value':'hello'}) == BackendToolCall(
        tool_name='fill',arguments={'pageId':3,'uid':'1_6','value':'hello','includeSnapshot':False})
    for args in ({'uid':''},{'uid':'1_5','dblClick':True},{'uid':'1_5','x':4}):
        with pytest.raises(BackendContractError):
            project_backend_call('click',page_id=3,arguments=args)
    with pytest.raises(BackendContractError):
        project_backend_call('fill',page_id=3,arguments={'uid':'1_6','value':'x'*16385})


def test_keyboard_surface_is_narrow_and_does_not_accept_modifier_scripts():
    assert project_backend_call('type_text',page_id=2,arguments={'text':'abc'}) == BackendToolCall(
        tool_name='type_text',arguments={'pageId':2,'text':'abc'})
    assert project_backend_call('press_key',page_id=2,arguments={'key':'Enter'}) == BackendToolCall(
        tool_name='press_key',arguments={'pageId':2,'key':'Enter','includeSnapshot':False})
    for value in ['', 'Control+Alt+Delete', 'Meta+Q', 'x'*65]:
        with pytest.raises(BackendContractError):
            project_backend_call('press_key',page_id=2,arguments={'key':value})


@pytest.mark.parametrize('url',['https://example.com/a','http://127.0.0.1:8080/x'])
def test_navigation_is_http_only_and_page_bound(url):
    call=project_backend_call('navigate_page',page_id=9,arguments={'url':url})
    assert call == BackendToolCall('navigate_page',{
        'pageId':9,'type':'url','url':url,'handleBeforeUnload':'dismiss'})
    assert 'initScript' not in call.arguments


@pytest.mark.parametrize('url',[
    'javascript:alert(1)','data:text/html,x','file:///etc/passwd',
    'https://user:pass@example.com/','https://example.com/\nnext',
])
def test_navigation_refuses_active_or_credential_urls(url):
    with pytest.raises(BackendContractError):
        project_backend_call('navigate_page',page_id=9,arguments={'url':url})


def test_wait_for_is_read_only_bounded_text_match():
    assert project_backend_call('wait_for',page_id=4,arguments={'text':['Ready']}) == BackendToolCall(
        'wait_for',{'pageId':4,'text':['Ready'],'timeout':5000})
    with pytest.raises(BackendContractError):
        project_backend_call('wait_for',page_id=4,arguments={'text':[]})
    with pytest.raises(BackendContractError):
        project_backend_call('wait_for',page_id=4,arguments={'text':['x'*1025]})


@pytest.mark.parametrize('tool',['evaluate_script','upload_file','new_page','select_page','shell',''])
def test_unknown_or_broad_backend_tools_refuse(tool):
    with pytest.raises(BackendContractError):
        project_backend_call(tool,page_id=1,arguments={})


def test_arguments_are_closed_and_inputs_are_not_mutated():
    args={'uid':'1_5'}
    before=dict(args)
    project_backend_call('click',page_id=1,arguments=args)
    assert args==before
    with pytest.raises(BackendContractError):
        project_backend_call('click',page_id=1,arguments={'uid':'1_5','unexpected':True})


def _tool_row(name, *, page_scoped=False, description='ignored'):
    properties={}
    required=[]
    if page_scoped:
        properties['pageId']={'type':'number','description':'Targets a specific page by ID.'}
        required.append('pageId')
    return {
        'name':name,
        'description':description,
        'inputSchema':{
            'type':'object',
            'properties':properties,
            'required':required,
            'additionalProperties':False,
        },
    }


def _complete_catalog():
    return {'tools':[
        _tool_row(name,page_scoped=name!='list_pages')
        for name in sorted(ALLOWED_BACKEND_TOOLS)
    ] + [_tool_row('evaluate_script',page_scoped=True)]}


def test_catalog_attestation_selects_only_closed_tools_and_binds_schema():
    catalog=_complete_catalog()
    attestation=attest_backend_catalog(catalog)
    assert attestation.selected_tools == tuple(sorted(ALLOWED_BACKEND_TOOLS))
    assert len(attestation.schema_digest)==64
    int(attestation.schema_digest,16)
    assert attestation.is_admission is False
    changed=_complete_catalog()
    next(row for row in changed['tools'] if row['name']=='click')['inputSchema']['properties']['uid']={'type':'string'}
    assert attest_backend_catalog(changed).schema_digest != attestation.schema_digest


def test_catalog_digest_ignores_noncontract_description_copy():
    first=_complete_catalog()
    second=_complete_catalog()
    for row in second['tools']:
        row['description']='different vendor prose'
    assert attest_backend_catalog(first).schema_digest == attest_backend_catalog(second).schema_digest


@pytest.mark.parametrize('missing', sorted(ALLOWED_BACKEND_TOOLS))
def test_catalog_attestation_refuses_missing_selected_tool(missing):
    catalog=_complete_catalog()
    catalog['tools']=[row for row in catalog['tools'] if row['name']!=missing]
    with pytest.raises(BackendContractError):
        attest_backend_catalog(catalog)


@pytest.mark.parametrize('name', sorted(ALLOWED_BACKEND_TOOLS-{'list_pages'}))
def test_page_scoped_selected_tool_must_require_page_id(name):
    catalog=_complete_catalog()
    row=next(row for row in catalog['tools'] if row['name']==name)
    row['inputSchema']['required']=[]
    with pytest.raises(BackendContractError):
        attest_backend_catalog(catalog)


def test_catalog_attestation_refuses_duplicate_names_and_malformed_schema():
    catalog=_complete_catalog()
    catalog['tools'].append(dict(catalog['tools'][0]))
    with pytest.raises(BackendContractError):
        attest_backend_catalog(catalog)
    catalog=_complete_catalog()
    next(row for row in catalog['tools'] if row['name']=='click')['inputSchema']=[]
    with pytest.raises(BackendContractError):
        attest_backend_catalog(catalog)
