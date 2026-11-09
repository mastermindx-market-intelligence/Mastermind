"""The three fixed knowledge READ paths extend the exact public edge profile; the later source-operation and project-control READs extend it further."""
from pathlib import Path
from ops.executive_os.os_public_edge import (GET_ROUTES,POST_ROUTES,PRE_PROJECT_KNOWLEDGE_GET_ROUTES,PROJECT_KNOWLEDGE_GET_ROUTES,PRE_INSTRUCTION_ADMISSION_POST_ROUTES,TRANSITION_ROUTE_PROFILES,PRE_AUTHORIZATION_IDENTITY_GET_ROUTES,AUTHORIZATION_IDENTITY_GET_ROUTES,_TEMPLATE)

def test_three_fixed_read_routes_preserve_the_whole_predecessor_profile():
 expected={"/workspace/project-knowledge/current","/workspace/project-memory/current","/workspace/project-source/current"}
 source_operation_reads={"/workspace/source-operation/context","/workspace/source-operation/operation"}
 control_reads={"/workspace/project-instructions/current", "/workspace/instruction-admission/current",
                "/workspace/instruction-admission/operation", "/workspace/project-access/current", '/workspace/source-operation/options', '/workspace/resources/host-observation/current', '/workspace/mission-result/current', '/workspace/native-draft-identity/current', '/workspace/byok/roles/current'}
 assert set(PROJECT_KNOWLEDGE_GET_ROUTES)==expected
 assert set(PRE_AUTHORIZATION_IDENTITY_GET_ROUTES)-set(PRE_PROJECT_KNOWLEDGE_GET_ROUTES)==expected|source_operation_reads|control_reads
 assert GET_ROUTES == PRE_AUTHORIZATION_IDENTITY_GET_ROUTES + AUTHORIZATION_IDENTITY_GET_ROUTES
 assert (PRE_PROJECT_KNOWLEDGE_GET_ROUTES,PRE_INSTRUCTION_ADMISSION_POST_ROUTES) in TRANSITION_ROUTE_PROFILES
 template=_TEMPLATE.read_text();get=template.split('@get {',1)[1].split('handle @get',1)[0];post=template.split('@post {',1)[1].split('handle @post',1)[0]
 root=Path(__file__).resolve().parents[1];gateway=(root/'integrations/executive_mcp/server.py').read_text()
 for route in expected:
  assert GET_ROUTES.count(route)==1 and route not in POST_ROUTES and get.count(route)==1 and route not in post
  assert gateway.count('"'+route+'"')==3
 for route in source_operation_reads|control_reads:
  assert GET_ROUTES.count(route)==1 and route not in POST_ROUTES and get.count(route)==1 and route not in post
