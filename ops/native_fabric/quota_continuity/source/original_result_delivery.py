"""Retain one admitted original run through the incumbent bounded read transport."""
import argparse
import os
from pathlib import Path
import subprocess
import time

import artifact_delivery as delivery
import original_result_read as current


def qualify(request):
    evidence = current.qualify(request)
    paths = [Path(__file__), delivery.HERE / "fabric_task.py",
             delivery.HERE / "remote_sub.sh", delivery.HERE / "run_observation_delivery.py"]
    raw = {path.name: delivery.local_file(path, 1048576) for path in paths}
    if any(delivery.local_file(path, 1048576) != raw[path.name] for path in paths):
        raise ValueError("current_output_carrier_sources_changed")
    return {"read": evidence, "carrier_sources_sha256":
            {key: current.digest(value) for key, value in raw.items()}}


def export(request, destination):
    evidence = qualify(request)
    chain = delivery.reserve_destination(destination)
    receipt = {"schema": "mastermind.original_result_current_delivery_receipt.v1",
               "request": request, "evidence": evidence, "state": "READ_PENDING",
               "read_transport_state": "MAY_START_AFTER_THIS_INTENT", "files": [],
               "retained": None, **current.FALSE_CLAIMS}
    retained_chain = None
    retained_receipt_inode = None
    retained_file_inodes = {}
    def unchanged():
        if qualify(request) != evidence:
            raise ValueError("current_output_sources_changed")
    def verify_publication():
        try:
            unchanged()
            if receipt["state"] == "CURRENT_BYTES_AVAILABLE":
                if retained_chain is None or receipt["retained"] is None:
                    raise ValueError("retained_current_output_unavailable")
                retained_chain.verify()
                delivery.verify_delivered(retained_chain, receipt["retained"]["files"])
                for name, expected in retained_file_inodes.items():
                    if delivery.inode(os.stat(name, dir_fd=retained_chain.fd,
                                               follow_symlinks=False)) != expected:
                        raise ValueError("retained_current_file_replaced")
                if (delivery.inode(os.stat("receipt.json", dir_fd=retained_chain.fd,
                                         follow_symlinks=False)) != retained_receipt_inode
                        or delivery.read_local_at(retained_chain, "receipt.json", 65536)
                           != current.canonical(receipt["retained"])):
                    raise ValueError("retained_current_receipt_changed")
        except Exception:
            receipt["retained"] = None
            receipt["state"] = "UNAVAILABLE"
            raise
    try:
        delivery.write_exclusive(chain.fd, "request.json", current.canonical(receipt))
        try:
            unchanged()
            chain.verify()
            receipt["read_transport_state"] = "ATTEMPTED_UNCONFIRMED"
            raw = delivery.transport(evidence["read"]["original_read_evidence"]["ssh_alias"], request,
                current_sources_sha256=evidence["read"]["read_sources_sha256"])
            receipt["read_transport_state"] = "RESPONSE_RECEIVED"
            current.validate_response(raw, request)
            unchanged()
            chain.verify()
            receipt["retained"] = current.retain_response(request, raw,
                str(Path(destination) / "current-bytes"), expected_evidence=evidence["read"])
            retained_chain = delivery.DirectoryChain(Path(destination) / "current-bytes")
            retained_receipt_inode = delivery.inode(os.stat("receipt.json", dir_fd=retained_chain.fd,
                                                           follow_symlinks=False))
            retained_file_inodes = {entry["local_name"]: delivery.inode(os.stat(entry["local_name"],
                dir_fd=retained_chain.fd, follow_symlinks=False)) for entry in receipt["retained"]["files"]}
            unchanged()
            chain.verify()
            receipt["state"] = "CURRENT_BYTES_AVAILABLE"
            verify_publication()
        except (OSError, ValueError, TypeError, KeyError, RecursionError, OverflowError, subprocess.SubprocessError):
            receipt["state"] = "UNAVAILABLE"
            receipt["retained"] = None
        receipt["observed_at_epoch"] = time.time()
        delivery.publish_receipt(chain, receipt, {"paths": []}, verify_source=verify_publication)
        return receipt
    finally:
        if retained_chain is not None:
            retained_chain.close()
        chain.close()


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("run_id")
    p.add_argument("--root", required=True)
    p.add_argument("--destination", required=True)
    args = p.parse_args(argv)
    try:
        receipt = export(current.request_for(args.run_id, args.root), args.destination)
        print(current.canonical(receipt).decode())
        return 0 if receipt["state"] == "CURRENT_BYTES_AVAILABLE" else 76
    except (OSError, ValueError, TypeError, KeyError, RecursionError, OverflowError, subprocess.SubprocessError):
        print('{"state":"REFUSED","reason":"original_current_output_unconfirmed"}')
        return 75
