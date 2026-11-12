"""Work jobs must stop on cancellation without weakening the final test gate."""

from pathlib import Path
import re

import pytest
import yaml

from scripts import ci_parallel_shard as fan
from scripts import ci_pytest as cip


_WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/ci.yml"


def _replace_in_job(text, job, old, new):
    """Replace ``old`` exactly once inside one top-level job's block.

    The qualification lane deliberately shares the full-shard predicate, so a
    whole-file replacement would mutate two jobs at once.
    """
    start = text.index(f"\n  {job}:\n")
    following = re.search(r"\n  [A-Za-z_][\w-]*:\n", text[start + 1:])
    end = len(text) if following is None else start + 1 + following.start()
    section = text[start:end]
    assert section.count(old) == 1
    return text[:start] + section.replace(old, new) + text[end:]


@pytest.mark.parametrize("job", ["pr_fast", "pytest_shards", "qualification", "native_admission"])
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
    with pytest.raises(cip.PolicyError):
        fan.validate_parallel_workflow(_replace_in_job(text, job, predicate, unsafe))
