"""Paused Hermes cron catalog. Loading it does not install or tick anything."""

from __future__ import annotations

import json
from pathlib import Path


CATALOG_PATH = Path(__file__).with_name("routines") / "jobs.json"


class CatalogError(ValueError):
    pass


def load_catalog(path: Path | None = None) -> dict:
    target = path or CATALOG_PATH
    catalog = json.loads(target.read_text(encoding="utf-8"))
    if catalog.get("installed") is not False:
        raise CatalogError("catalog must stay uninstalled")
    if len(catalog.get("jobs", [])) != 7:
        raise CatalogError("catalog must carry the seven secretary routines")
    return catalog


def install_into_hermes_home(*_args: object, **_kwargs: object) -> None:
    raise RuntimeError("REFUSING_LIVE_CRON_INSTALL")


def hermes_create_kwargs(job: dict) -> dict:
    """Fields a future caller could pass to Hermes ``create_job``.

    The returned job is paused and delivers locally. This function does not
    call Hermes.
    """

    if job.get("schedule_backend") != "hermes_cron":
        raise ValueError("NOT_A_HERMES_CRON_JOB")
    schedule = job.get("hermes_schedule")
    if not isinstance(schedule, str) or not schedule:
        raise ValueError("NOT_A_HERMES_CRON_JOB")
    if job.get("deliver") != "local" or job.get("enabled") is not False:
        raise CatalogError("shadow jobs stay paused and local")
    return {
        "name": job["name"],
        "prompt": job["prompt"],
        "schedule": schedule,
        "deliver": "local",
        "paused": True,
        "paused_reason": job["paused_reason"],
        "skills": list(job.get("skills") or []),
        "no_agent": False,
    }
