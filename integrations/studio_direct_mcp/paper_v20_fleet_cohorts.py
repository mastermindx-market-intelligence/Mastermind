"""Static, read-only identity pins for the eight existing M2 Paper legacy cohorts.

This is data/plan validation inside the original private_service owner: not a
lifecycle, credential, writer, installer, retry, approval, or gateway plane.
Callers MUST use existing _verify_staged_install and the reviewed stopped-
service _apply_paper_selection transaction; this module never touches disk.
No account is admitted based on version alone or from a caller-supplied path.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

TARGET_GENERATION = "v20"
TARGET_BRIDGE_SHA256 = "1a73ab002e89c87b489e8cee9f5c821530929a5b701eb0aaac7eed03a5a22ced"
PREDECESSORS = {"v10": "7d810c458a53e00e21014fd7375ac338dc9c1421b30f823feb4d34184f9d08fc", "v12": "82bc7f2d75aec423711922198b68f317618a83de177bf4934b73d7b418a6ecfb"}
COHORTS = {
    "admin-business": {
        "bridge_sha256": "7d810c458a53e00e21014fd7375ac338dc9c1421b30f823feb4d34184f9d08fc",
        "config_sha256": "2f0fd933062a0168093caa6a675dc27c91746837701fd28d74b7baf5ff3f4863",
        "file_count": 11,
        "generation": "v10",
        "manifest_sha256": "35903622d2e10b3ba56aedbf64cc2484d8b53bdb67ab71a8e0f9b0b7ebacc148",
        "nonpaper_sha256": "51167dbb4b3f5c763ba7ff389c839706449410de4ba845e5fa92fa033788c974",
        "plist_sha256": "bb3d1e89c9c99cedf4f80c9874170ce1b4ccc83c2441f9f051bf3386fafd97b8"
    },
    "chatgpt1": {
        "bridge_sha256": "7d810c458a53e00e21014fd7375ac338dc9c1421b30f823feb4d34184f9d08fc",
        "config_sha256": "80e8d8dccc4dfef56f091bd86e01925f8cd640f7d89caf09f7c2693e78e66633",
        "file_count": 12,
        "generation": "v10",
        "manifest_sha256": "f05c412f1a5e9076b5804aed547b1c85cfc9f00dcea0c4c2342698f20eac9aa1",
        "nonpaper_sha256": "5748e8b06ffe17f71c9c17164591ee835efcce8f1682f7daf6ea7552c092b7c5",
        "plist_sha256": "a80e4013e55e5098e7d4e5c699c340cbe80128d17e2c5456551e27fe10ba8254"
    },
    "chatgpt2-business": {
        "bridge_sha256": "7d810c458a53e00e21014fd7375ac338dc9c1421b30f823feb4d34184f9d08fc",
        "config_sha256": "195b1bc4f54d51906740758977788f697fccb81a1e74c964bfc648250376f7ef",
        "file_count": 12,
        "generation": "v10",
        "manifest_sha256": "9f2f1cdecdd99b1673181b0109d8e6b11896d95541ad42d5e087fb64c2646d3b",
        "nonpaper_sha256": "46a17fadcca54cd42c48627b0e6e2416f5b65e18df082882c7d73d42efbf90bb",
        "plist_sha256": "17c15337cd87a7e5e0da664db4bf4f0156e7386ded3f2d09c5a3eca11068fdc2"
    },
    "chatgpt3": {
        "bridge_sha256": "7d810c458a53e00e21014fd7375ac338dc9c1421b30f823feb4d34184f9d08fc",
        "config_sha256": "4e40de0d38d689dc9eabc64d1ec50ae552681ba0880b7d3d0fd0f973a3d2507b",
        "file_count": 12,
        "generation": "v10",
        "manifest_sha256": "f826239592b62512dbbcd3f3546facc71e1d3696bdda150666711d50d6ae20f7",
        "nonpaper_sha256": "43267beac57061406111bacb1d8a1b01f5113857fe7390aaf5ee900f6d5837ab",
        "plist_sha256": "540542289bbd1b5530f18cab75210ce762de3b17e07a923093a38d6c5ada8a2b"
    },
    "chatgpt3-w570f6f34": {
        "bridge_sha256": "7d810c458a53e00e21014fd7375ac338dc9c1421b30f823feb4d34184f9d08fc",
        "config_sha256": "6e527360ba76034d0bde30943cb1025f82489525445bcac2ab86c8b190df8fbc",
        "file_count": 11,
        "generation": "v10",
        "manifest_sha256": "aa24bddbad7e989cedf566f4fbf4288fa333ee8fac8d2585cdcd9c954736eab3",
        "nonpaper_sha256": "b8df161b9b0e4d0aab38600a8b84994580ba77dad69b408b2f534cbf919e29aa",
        "plist_sha256": "cd776537e64f10487261ac78147743fdbcfaef06cab5bc39cebb464452abddd6"
    },
    "chatgpt3-wa2a9e6f9": {
        "bridge_sha256": "7d810c458a53e00e21014fd7375ac338dc9c1421b30f823feb4d34184f9d08fc",
        "config_sha256": "4e9aad915c1ea46e5de79c158d233d911e5aef7832d2016a2616a2996fa8fa68",
        "file_count": 11,
        "generation": "v10",
        "manifest_sha256": "38d5427f418f9f3f7aa1ff671befa55555f276cd4b639a6312e24fa0672965a3",
        "nonpaper_sha256": "7a4f7a60786287d07fa39b93f7d87ba81467b90fbb6dd286ad985ec054f90e09",
        "plist_sha256": "12357a27fdd3d957b83cc4ce83262bdccc66bd17005d00248d2da9749537f6e7"
    },
    "chatgpt4": {
        "bridge_sha256": "82bc7f2d75aec423711922198b68f317618a83de177bf4934b73d7b418a6ecfb",
        "config_sha256": "f02e385e234f7f88619058485b61f17834d3cfc33896ce3f5606bd64fcecce21",
        "file_count": 11,
        "generation": "v12",
        "manifest_sha256": "168bb25afd7d710799fb86f8912389d49c86371c107ee9544d65fdc2b9d390e2",
        "nonpaper_sha256": "ca96e5c56f39d8c040dfe55b392add75c3c496c57f7e0f499b638595f83bebca",
        "plist_sha256": "b63dcc9017b61553888b95d9ffc68c572020ef02b74e73ee60c990ed1f89fe16"
    },
    "mastermind-os-publication": {
        "bridge_sha256": "82bc7f2d75aec423711922198b68f317618a83de177bf4934b73d7b418a6ecfb",
        "config_sha256": "6b1f07a31e207828473f0f387515db02139731aaa1508bd8d34bc826a2753f11",
        "file_count": 13,
        "generation": "v12",
        "manifest_sha256": "bd9dfc4e315541085342c410f0575ddbba0d40afb9d0208709078bf9b3b0c9ed",
        "nonpaper_sha256": "c0faa52703c8e670b47427bb66a74adbf24cb55ef0586164a70c9975e8234b8b",
        "plist_sha256": "525ed99524c4fa060a8d8ada0967b06509c42f970270f8b2619537516ebfdb34"
    }
}


# A separately reviewed, exact post-#1992 C4 publisher-enrollment
# predecessor. This is one alternate sealed state of the SAME chatgpt4
# account, not a ninth seat, new installer or permission expansion.
# It is eligible only after the original enrollment owner authenticates
# its committed result and native-pool selection at the call site.
C4_POST_ENROLLMENT = {
    "bridge_sha256": PREDECESSORS["v12"],
    "config_sha256": "37680eb009b4199ffba209e0d88775b73e00a4ca0ca8f0785a22d33ec2d81d2b",
    "file_count": 12,
    "generation": "v12",
    "manifest_sha256": "3648a9a8e9711bab7be9fc7a3950f73579ce7d78358a18c15ac7d39adf924a9f",
    "nonpaper_sha256": "12ae346e48d5215654a0040eaa61c82ce8cdea7f4618ac462d294c5fd394d8b2",
    "plist_sha256": COHORTS["chatgpt4"]["plist_sha256"],
}



# Exact newer 12-file incumbents already installed by existing Studio
# Git/Workspace publishers after original Paper v20's 11-file freeze.
# These preserve workspace-access.mjs and every non-Paper byte. Selection is
# allowed only for the same three original seats at their exact sealed
# manifest/config/plist preimages; the original COHORTS remain immutable.
WORKSPACE_12FILE_SUCCESSORS = {
    "admin-business": {
        "bridge_sha256": "7d810c458a53e00e21014fd7375ac338dc9c1421b30f823feb4d34184f9d08fc",
        "config_sha256": "76e093610040209dd788297c99b9d82da557edce13f83bcb2fcc5a2b8a9c4ba1",
        "file_count": 12,
        "generation": "v10",
        "manifest_sha256": "dab1561865cbbf8db10000b655bb33e803201103af76167801159e9b31f5f8e1",
        "nonpaper_sha256": "3aa7a35697b2b23f67bda0d71328cc69d83d20ae4a8149e1eb02627ffe79df0c",
        "plist_sha256": "bb3d1e89c9c99cedf4f80c9874170ce1b4ccc83c2441f9f051bf3386fafd97b8"
    },
    "chatgpt3-w570f6f34": {
        "bridge_sha256": "7d810c458a53e00e21014fd7375ac338dc9c1421b30f823feb4d34184f9d08fc",
        "config_sha256": "16f49e1eea18266664b68fb2f3f4cda4a2f26e25eec9d0b0a08cdcf5f384b1dd",
        "file_count": 12,
        "generation": "v10",
        "manifest_sha256": "0f6b3d5f846ac33b27be7ff38c90f630db044c2b399a7e6ac3b064ce7a89eae2",
        "nonpaper_sha256": "80e3f6975c2dbdd520e8498ef0106c2403ea7c34f2f8c082dd91e34d361dbce4",
        "plist_sha256": "cd776537e64f10487261ac78147743fdbcfaef06cab5bc39cebb464452abddd6"
    },
    "chatgpt3-wa2a9e6f9": {
        "bridge_sha256": "7d810c458a53e00e21014fd7375ac338dc9c1421b30f823feb4d34184f9d08fc",
        "config_sha256": "4d713656ffd06ba577b210e3faad28ff2581986678f86f58320029ba7d3ddd51",
        "file_count": 12,
        "generation": "v10",
        "manifest_sha256": "f1a6f856d87a841f7c7213a229e092ebdcdcba0c3763d27c76d32216bf9ad8cb",
        "nonpaper_sha256": "cf6a6f719c62d75e77f1b28d698ea47ad4a57c47f8119efc7bf996c359e204bf",
        "plist_sha256": "12357a27fdd3d957b83cc4ce83262bdccc66bd17005d00248d2da9749537f6e7"
    }
}


def _sha(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _canonical_hash(obj: dict) -> str:
    return _sha(json.dumps(obj,sort_keys=True,separators=(",",":")).encode("utf-8"))


def plan_selection(account: str, *, manifest_bytes: bytes, config_bytes: bytes,
                   plist_bytes: bytes, home: Path) -> dict:
    """Plan exact Paper-only v20 selection from a pinned original installation.

    The *caller*, not this pure planner, must verify installed files/dependencies,
    inspect original launchd state, serialize via the original lifecycle lock,
    CAS the old manifest before commit, preserve effects and reconcile timeouts.
    """
    pin = COHORTS.get(account)
    if (account == "chatgpt4" and type(account) is str
            and _sha(manifest_bytes) == C4_POST_ENROLLMENT["manifest_sha256"]):
        pin = C4_POST_ENROLLMENT
    if (type(account) is str and account in WORKSPACE_12FILE_SUCCESSORS
            and _sha(manifest_bytes) ==
                    WORKSPACE_12FILE_SUCCESSORS[account]["manifest_sha256"]):
        pin = WORKSPACE_12FILE_SUCCESSORS[account]
    if pin is None or type(account) is not str:
        raise ValueError("Paper fleet account is not in the reviewed cohort")
    if (_sha(manifest_bytes) != pin["manifest_sha256"]
            or _sha(config_bytes) != pin["config_sha256"]
            or _sha(plist_bytes) != pin["plist_sha256"]):
        raise ValueError("Paper fleet predecessor CAS or service identity changed")
    try:
        manifest=json.loads(manifest_bytes)
        original=json.loads(config_bytes)
    except (ValueError,UnicodeError) as exc:
        raise ValueError("Paper fleet predecessor JSON invalid") from exc
    label="com.mastermind.studio-direct-private."+account
    if (type(manifest) is not dict or type(original) is not dict
            or manifest.get("version") != 2 or manifest.get("account") != account
            or manifest.get("label") != label
            or type(manifest.get("files")) is not dict
            or len(manifest["files"]) != pin["file_count"]
            or manifest.get("configHash") != pin["config_sha256"]
            or manifest.get("plistHash") != pin["plist_sha256"]):
        raise ValueError("Paper fleet manifest identity or seal changed")
    nonpaper={k:v for k,v in original.items() if k!="paperDesign"}
    if _canonical_hash(nonpaper) != pin["nonpaper_sha256"]:
        raise ValueError("Paper fleet non-Paper configuration changed")
    generation=pin["generation"]
    if pin["bridge_sha256"] != PREDECESSORS.get(generation):
        raise ValueError("Paper fleet predecessor bridge not reviewed")
    home=Path(home)
    old_runtime=home/".local/share/mastermind-paper/runtime"/generation
    expected_old={
        "enabled":True,
        "pythonPath":str(old_runtime/"venv/bin/python"),
        "bridgePath":str(old_runtime/"source/bridge.py"),
        "bridgeSha256":pin["bridge_sha256"],
        "appPath":str(home/"Applications/Paper.app"),
        "commandTimeoutMs":70000,
    }
    if original.get("paperDesign") != expected_old:
        raise ValueError("Paper fleet selected predecessor differs")
    future_runtime=home/".local/share/mastermind-paper/runtime"/TARGET_GENERATION
    target={**expected_old,
            "pythonPath":str(future_runtime/"venv/bin/python"),
            "bridgePath":str(future_runtime/"source/bridge.py"),
            "bridgeSha256":TARGET_BRIDGE_SHA256}
    future_config=json.dumps({**original,"paperDesign":target},indent=2,sort_keys=True).encode("utf-8")
    future_manifest={**manifest,"configHash":_sha(future_config)}
    future_manifest_bytes=json.dumps(future_manifest,indent=2,sort_keys=True).encode("utf-8")
    return {
        "account":account,"label":label,"fromGeneration":generation,
        "toGeneration":TARGET_GENERATION,"bridgeSha256":TARGET_BRIDGE_SHA256,
        "originalManifestSha256":pin["manifest_sha256"],
        "targetManifestSha256":_sha(future_manifest_bytes),
        "nonPaperConfigSha256":pin["nonpaper_sha256"],
        "preservedGatewayFiles":pin["file_count"],
        "serviceStarted":False,
        "configBytes":future_config,"manifestBytes":future_manifest_bytes,
        "manifest":future_manifest,
    }
