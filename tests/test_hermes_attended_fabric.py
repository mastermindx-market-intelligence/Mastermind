"""Enroll the native Fabric bridge in the existing protected pytest suite.

Import the same contract cases used by package-local unittest discovery so
PR-head and integrated merge-group CI exercise the production boundary.
"""
from integrations.hermes_attended_fabric.tests.test_native import TestNativeFabric
from integrations.hermes_attended_fabric.tests.test_facade_port import TestFabricFacadePort
from integrations.hermes_attended_fabric.tests.test_hermes_mcp_client import TestNativeHermesMcpClient
from integrations.hermes_attended_fabric.tests.test_return_currentness import (
    TestComposedReturnCurrentness, TestNativeReturnCurrentness,
)
from integrations.hermes_attended_fabric.tests.test_facade_wire_integration import TestFacadeWireIntegration
