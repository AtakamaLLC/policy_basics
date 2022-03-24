import unittest.mock
from multiprocessing.pool import ThreadPool

import atakama
import notanorm
import pytest
from atakama import ProfileInfo, ApprovalRequest, RequestType

from tests.test_time_range import local_parse

from policy_basics.per_profile_throttle import (
    ProfileThrottleRule,
    ProfileThrottleDb,
    ProfileCount,
)
from policy_basics.simple_db import FileDb


def set_time(timer, iso):
    timer.now.return_value = local_parse(iso)
    timer.time.return_value = local_parse(iso).timestamp()


@pytest.mark.parametrize("persistent", [True, False])
def test_profile_throttle(tmp_path, persistent):
    path = tmp_path / "quote.db"
    pr = ProfileThrottleRule(
        {
            "per_day": 3,
            "per_hour": 1,
            "persistent": persistent,
            "rule_id": "rid",
            "db-file": path,
        }
    )
    pr.clear_quota(ProfileInfo(profile_id=b"pid", profile_words=[]))
    with unittest.mock.patch("policy_basics.per_profile_throttle.Timer") as timer:
        # fixed time
        set_time(timer, "2022-03-09 17:00Z")

        pi = ProfileInfo(profile_id=b"pid", profile_words=[])
        assert not pr.at_quota(pi)
        # same hour
        assert pr._approve_profile_request(b"pid")
        assert pr.at_quota(pi)
        assert not pr._approve_profile_request(b"pid")

        # new hour
        set_time(timer, "2022-03-09 18:00Z")

        # 3rd req ok for the day
        assert pr._approve_profile_request(b"pid")

        # not 4th
        assert not pr._approve_profile_request(b"pid")

        # 2nd day
        set_time(timer, "2022-03-10 00:00Z")
        assert pr._approve_profile_request(b"pid")

        # 2nd day same hour
        assert not pr._approve_profile_request(b"pid")

        # 2nd day new hours
        set_time(timer, "2022-03-10 01:00Z")
        assert pr._approve_profile_request(b"pid")
        set_time(timer, "2022-03-10 02:00Z")
        assert pr._approve_profile_request(b"pid")
        set_time(timer, "2022-03-10 03:00Z")
        assert not pr._approve_profile_request(b"pid")

        # top level
        assert not pr.approve_request(
            ApprovalRequest(
                request_type=None,
                device_id=b"pid",
                profile=ProfileInfo(profile_id=b"pid", profile_words=[]),
                auth_meta=None,
                cryptographic_id=None,
            )
        )

        # 3rd day
        set_time(timer, "2022-03-11 00:00Z")
        assert pr.approve_request(
            ApprovalRequest(
                request_type=None,
                device_id=b"pid",
                profile=ProfileInfo(profile_id=b"pid", profile_words=[]),
                auth_meta=None,
                cryptographic_id=None,
            )
        )


def test_persistent():
    pr = ProfileThrottleRule({"per_day": 3, "persistent": True, "rule_id": "rid"})
    pr.clear_quota(ProfileInfo(profile_id=b"pid", profile_words=[]))
    pr2 = ProfileThrottleRule(
        {"per_day": 3, "persistent": True, "rule_id": "different_rule"}
    )
    pr2.clear_quota(ProfileInfo(profile_id=b"pid", profile_words=[]))

    assert pr._approve_profile_request(b"pid")
    assert pr._approve_profile_request(b"pid")
    assert pr._approve_profile_request(b"pid")
    pr = ProfileThrottleRule({"per_day": 3, "persistent": True, "rule_id": "rid"})
    assert not pr._approve_profile_request(b"pid")

    # different rule is unaffected
    assert pr2._approve_profile_request(b"pid")


@pytest.mark.parametrize("persistent", [False, True])
def test_throttle_atomic(tmp_path, persistent):
    path = tmp_path / "quote.db"
    with unittest.mock.patch("policy_basics.per_profile_throttle.Timer") as timer:
        set_time(timer, "2022-03-09 17:00Z")
        pr = ProfileThrottleRule(
            {
                "per_day": 50,
                "per_hour": 50,
                "persistent": persistent,
                "rule_id": "rid",
                "db-file": path,
            }
        )

        thread_pool = ThreadPool(10)

        cnt = 100
        approves = 0

        def sets(_):
            nonlocal approves
            if pr._approve_profile_request(b"pid"):
                approves += 1

        thread_pool.map(sets, range(cnt))

        assert approves == 50


def test_throttle_db_corruption(tmp_path):
    # resilient to file corruption, just resets counts
    path = tmp_path / "quote.db"
    with path.open("w") as db_fh:
        db_fh.write("junk")
    db = ProfileThrottleDb({"persistent": True, "db-file": path, "rule_id": "rid"})
    assert db.increment("rid", b"pid", db.get("rid", b"pid")).day_cnt == 1


def test_throttle_db_schema_bad(tmp_path):
    # resilient to schema changes, just resets counts
    path = tmp_path / "quote.db"
    with notanorm.SqliteDb(str(path)) as db:
        db.query("create table %s (ajunk, bjunk)" % FileDb.TABLE_NAME)
    db = ProfileThrottleDb({"persistent": True, "db-file": path, "rule_id": "rid"})
    assert db.increment("rid", b"pid", db.get("rid", b"pid")).day_cnt == 1


@pytest.fixture()
def throt_db(tmp_path):
    path = tmp_path / "quote.db"
    db = ProfileThrottleDb({"persistent": True, "db-file": path, "rule_id": "rid"})
    yield db


def test_throttle_db_weird_data(throt_db):
    bad_dct = {"tm": None, "hr": "wot", "dy": 3}
    assert throt_db.increment("rid", b"pid", throt_db.get("rid", b"pid")).day_cnt == 1
    throt_db.db.set(
        ProfileThrottleDb._get_db_key("rid", b"pid"), ProfileCount._dict_to_str(bad_dct)
    )
    assert throt_db.increment("rid", b"pid", throt_db.get("rid", b"pid")).day_cnt == 1


def test_throttle_db_schema_change(throt_db):
    bad_dct = {"tim": 1, "hr": 1, "dy": 3}
    assert throt_db.increment("rid", b"pid", throt_db.get("rid", b"pid")).day_cnt == 1
    throt_db.db.set(
        ProfileThrottleDb._get_db_key("rid", b"pid"), ProfileCount._dict_to_str(bad_dct)
    )
    assert throt_db.increment("rid", b"pid", throt_db.get("rid", b"pid")).day_cnt == 1


def test_end_to_end():
    cfg = {"decrypt": [[{"rule": "per-profile-throttle-rule", "per_day": 2}]]}
    rule_engine = atakama.RuleEngine.from_dict(cfg)
    assert rule_engine.approve_request(
        ApprovalRequest(
            request_type=RequestType.DECRYPT,
            device_id=b"pid",
            profile=ProfileInfo(profile_id=b"pid", profile_words=[]),
            auth_meta=None,
            cryptographic_id=None,
        )
    )
