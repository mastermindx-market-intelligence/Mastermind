"""Work jobs must stop on cancellation without weakening the final test gate."""

from pathlib import Path
import re

import pytest
import yaml

from scripts import ci_parallel_shard as fan
from scripts import ci_pytest as cip


_WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/ci.yml"


@pytest.mark.parametrize("job", ["pr_fast", "pytest_shards", "source_qualification", "source_qualification_fabric", "source_qualification_native"])
@pytest.mark.parametrize("unsafe_status", ["always()", "true"])
def test_work_job_cannot_ignore_workflow_cancellation(job, unsafe_status):
    text = _WORKFLOW.read_text(encoding="utf-8")
    workflow = yaml.load(text, Loader=cip._WorkflowYAMLLoader)
    predicate = workflow["jobs"][job]["if"]
    # Preserve the actual fast/full routing predicate while restoring the
    # cancellation-immune regression (or removing its status guard entirely).
    unsafe, count = re.subn(
        r"^\$\{\{ (?:always\(\)|!cancelled\(\)) && ",
        "${{ " + unsafe_status + " && ",
        predicate,
    )
    assert count == 1
    workflow["jobs"][job]["if"] = unsafe
    with pytest.raises(cip.PolicyError):
        fan.validate_parallel_workflow(yaml.safe_dump(workflow, sort_keys=False))
