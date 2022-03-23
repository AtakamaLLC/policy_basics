import os

import atakama
from atakama import ProfileInfo, ApprovalRequest, RequestType

from policy_basics.profile_id import (
    ProfileIdRule,
)


def test_profile_id_match():
    pid = os.urandom(16)
    hexpid = pid.hex()
    pr = ProfileIdRule(
        {"profile_ids": ["word list here is ok", hexpid], "rule_id": "rid"}
    )
    assert pr.approve_request(
        ApprovalRequest(
            request_type=None,
            device_id=b"whatever",
            profile=ProfileInfo(profile_id=pid, profile_words=["random", "words"]),
            auth_meta=None,
            cryptographic_id=None,
        )
    )

    assert pr.approve_request(
        ApprovalRequest(
            request_type=None,
            device_id=b"whatever",
            profile=ProfileInfo(
                profile_id=b"notpid",
                profile_words=[
                    "word",
                    "list",
                    "here",
                    "is",
                    "ok",
                    "later",
                    "words",
                    "ignored",
                ],
            ),
            auth_meta=None,
            cryptographic_id=None,
        )
    )

    assert not pr.approve_request(
        ApprovalRequest(
            request_type=None,
            device_id=b"whatever",
            profile=ProfileInfo(
                profile_id=b"notpid", profile_words=["word", "list", "here", "is"]
            ),
            auth_meta=None,
            cryptographic_id=None,
        )
    )


def test_end_to_end():
    pid = os.urandom(16)
    hexpid = pid.hex()
    cfg = {"decrypt": [[{"rule": "profile-id-rule", "profile_ids": [hexpid]}]]}
    rule_engine = atakama.RuleEngine.from_dict(cfg)
    assert rule_engine.approve_request(
        ApprovalRequest(
            request_type=RequestType.DECRYPT,
            device_id=b"profid",
            profile=ProfileInfo(profile_id=pid, profile_words=[]),
            auth_meta=None,
            cryptographic_id=None,
        )
    )
