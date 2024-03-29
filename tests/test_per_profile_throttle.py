# SPDX-FileCopyrightText: © Atakama, Inc <support@atakama.com>
# SPDX-License-Identifier: LGPL-3.0-or-later
import os
import time
import unittest.mock
from contextlib import contextmanager
from typing import Iterator

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
from policy_basics.simple_db import UriDb


def set_time(timer, iso):
    timer.now.return_value = local_parse(iso)
    timer.time.return_value = local_parse(iso).timestamp()


@contextmanager
def mysql_tmp_db_ctx() -> Iterator[str]:
    from notanorm.mysql import MySqlDb  # pylint: disable=import-outside-toplevel

    db_name = "txx_" + os.urandom(16).hex()

    mysql_cnf = os.path.expanduser("~/.my.cnf")
    try:
        with MySqlDb(read_default_file=mysql_cnf) as conn:
            conn.execute(f"create database {db_name}")
            conn.execute(f"use {db_name}")
        with MySqlDb(read_default_file=mysql_cnf, database=db_name) as conn:
            yield conn.uri
    finally:
        with MySqlDb(read_default_file=mysql_cnf) as conn:
            conn.execute(f"drop database {db_name}")


@pytest.fixture(params=["sqlite", "mysql"], name="db_uri")
def _db_uri(request, tmp_path):
    if request.param == "sqlite":
        path = tmp_path / "quote.db"
        yield "sqlite:" + str(path)
    else:
        with mysql_tmp_db_ctx() as db_uri:
            yield db_uri


@pytest.mark.parametrize("persistent", [True, False])
def test_throttle_basic(persistent, db_uri):
    pr = ProfileThrottleRule(
        {
            "per_day": 3,
            "per_hour": 1,
            "persistent": persistent,
            "rule_id": "rid",
            "db-uri": db_uri,
        }
    )
    pr.clear_quota(ProfileInfo(profile_id=b"pid", profile_words=[]))
    with unittest.mock.patch("policy_basics.per_profile_throttle.Timer") as timer:
        # fixed time
        set_time(timer, "2022-03-09 17:00Z")

        pi = ProfileInfo(profile_id=b"pid", profile_words=[])
        assert not pr.at_quota(pi)
        # same hour

        # approve_request call alone does not increment! Muse use_quota
        assert pr._approve_profile_request(b"pid")
        assert not pr.at_quota(pi)
        assert pr._approve_profile_request(b"pid")

        pr._use_quota(b"pid")
        assert pr.at_quota(pi)
        assert not pr._approve_profile_request(b"pid")

        # new hour
        set_time(timer, "2022-03-09 18:00Z")

        # 3rd req ok for the day
        assert pr._approve_and_use_quota(b"pid")

        # not 4th
        assert not pr._approve_and_use_quota(b"pid")

        # 2nd day
        set_time(timer, "2022-03-10 00:00Z")
        assert pr._approve_and_use_quota(b"pid")

        # 2nd day same hour
        assert not pr._approve_and_use_quota(b"pid")

        # 2nd day new hours
        set_time(timer, "2022-03-10 01:00Z")
        assert pr._approve_and_use_quota(b"pid")
        set_time(timer, "2022-03-10 02:00Z")
        assert pr._approve_and_use_quota(b"pid")
        set_time(timer, "2022-03-10 03:00Z")
        assert not pr._approve_and_use_quota(b"pid")

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
        req = ApprovalRequest(
            request_type=None,
            device_id=b"pid",
            profile=ProfileInfo(profile_id=b"pid", profile_words=[]),
            auth_meta=None,
            cryptographic_id=None,
        )
        assert pr.approve_request(req)
        pr.use_quota(req)

        assert not pr._approve_and_use_quota(b"pid")

        # 4th day but same hour of day
        set_time(timer, "2022-03-12 00:00Z")
        assert pr._approve_and_use_quota(b"pid")

        # Minutes later
        set_time(timer, "2022-03-12 00:08Z")
        assert not pr._approve_and_use_quota(b"pid")

        # Another profile
        assert pr._approve_and_use_quota(b"pid2")
        assert not pr._approve_and_use_quota(b"pid")
        set_time(timer, "2022-03-12 03:00Z")
        assert pr._approve_and_use_quota(b"pid2")
        assert pr._approve_and_use_quota(b"pid")
        set_time(timer, "2022-03-12 04:00Z")
        assert pr._approve_and_use_quota(b"pid")
        assert pr._approve_and_use_quota(b"pid2")
        assert not pr._approve_and_use_quota(b"pid")
        assert not pr._approve_and_use_quota(b"pid2")


def test_persistent():
    pr = ProfileThrottleRule({"per_day": 3, "persistent": True, "rule_id": "rid"})
    pr.clear_quota(ProfileInfo(profile_id=b"pid", profile_words=[]))
    pr2 = ProfileThrottleRule(
        {"per_day": 3, "persistent": True, "rule_id": "different_rule"}
    )
    pr2.clear_quota(ProfileInfo(profile_id=b"pid", profile_words=[]))

    assert pr._approve_and_use_quota(b"pid")
    assert pr._approve_and_use_quota(b"pid")
    assert pr._approve_and_use_quota(b"pid")
    pr = ProfileThrottleRule({"per_day": 3, "persistent": True, "rule_id": "rid"})
    assert not pr._approve_and_use_quota(b"pid")

    # different rule is unaffected
    assert pr2._approve_and_use_quota(b"pid")


def test_throttle_db_corruption(tmp_path):
    # sqlite is resilient to file corruption, just resets counts
    path = tmp_path / "quote.db"
    with path.open("w") as db_fh:
        db_fh.write("junk")
    db = ProfileThrottleDb({"persistent": True, "db-file": path, "rule_id": "rid"})
    assert db.increment("rid", b"pid", db.get("rid", b"pid", lock=False)).day_cnt == 1


def test_throttle_db_schema_bad(tmp_path):
    # sqlite is resilient to schema changes, just resets counts
    path = tmp_path / "quote.db"
    with notanorm.SqliteDb(str(path)) as db:
        db.query("create table %s (ajunk, bjunk)" % UriDb.TABLE_NAME)
    db = ProfileThrottleDb({"persistent": True, "db-file": path, "rule_id": "rid"})
    assert db.increment("rid", b"pid", db.get("rid", b"pid", lock=False)).day_cnt == 1


def test_throttle_db_uri_broken(db_uri):
    # sqlite is resilient to file corruption, just resets counts
    db = ProfileThrottleDb({"persistent": True, "db-uri": db_uri})
    db.db.db.execute("drop table %s" % db.db.table)
    db.db.db.query(
        "create table %s (`key` integer primary key, bjunk integer)" % UriDb.TABLE_NAME
    )
    with pytest.raises(notanorm.errors.DbError):
        ProfileThrottleDb({"persistent": True, "db-uri": db_uri})


def test_throttle_db_mem_not_persist(db_uri):
    # if persistence is off, it's not persistent
    db = ProfileThrottleDb({"persistent": False, "db-uri": db_uri})
    assert db.increment("rid", b"pid", db.get("rid", b"pid", lock=False)).day_cnt == 1
    db = ProfileThrottleDb({"persistent": False, "db-uri": db_uri})
    assert db.increment("rid", b"pid", db.get("rid", b"pid", lock=False)).day_cnt == 1


def test_throttle_custom_table(db_uri):
    # if persistence is off, it's not persistent
    db = ProfileThrottleDb({"persistent": True, "db-uri": db_uri, "db-table": "custom"})
    assert db.increment("rid", b"pid", db.get("rid", b"pid", lock=False)).day_cnt == 1
    assert db.db.table == "custom"


@pytest.fixture()
def throt_db(db_uri):
    db = ProfileThrottleDb({"persistent": True, "db-uri": db_uri, "rule_id": "rid"})
    yield db


def test_throttle_db_weird_data(throt_db, db_uri):
    bad_dct = {"tm": None, "hr": "wot", "dy": 3}
    assert (
        throt_db.increment(
            "rid", b"pid", throt_db.get("rid", b"pid", lock=False)
        ).day_cnt
        == 1
    )
    throt_db.db.set(
        ProfileThrottleDb._get_db_key("rid", b"pid"), ProfileCount._dict_to_str(bad_dct)
    )
    assert (
        throt_db.increment(
            "rid", b"pid", throt_db.get("rid", b"pid", lock=False)
        ).day_cnt
        == 1
    )

    db2 = ProfileThrottleDb({"persistent": True, "db-uri": db_uri, "rule_id": "rid"})
    throt_db.db.set(
        ProfileThrottleDb._get_db_key("rid", b"pid"), ProfileCount._dict_to_str(bad_dct)
    )
    prof_cnt = throt_db.get("rid", b"pid", lock=True)
    prof_cnt2 = db2.get("rid", b"pid", lock=False)
    assert db2.is_locked(prof_cnt2)
    prof_cnt = throt_db.increment("rid", b"pid", prof_cnt)
    assert prof_cnt.day_cnt == 1
    prof_cnt2 = db2.get("rid", b"pid", lock=False)
    assert not db2.is_locked(prof_cnt2)


def test_throttle_db_schema_change(throt_db):
    bad_dct = {"tim": 1, "hr": 1, "dy": 3}
    assert (
        throt_db.increment(
            "rid", b"pid", throt_db.get("rid", b"pid", lock=False)
        ).day_cnt
        == 1
    )
    throt_db.db.set(
        ProfileThrottleDb._get_db_key("rid", b"pid"), ProfileCount._dict_to_str(bad_dct)
    )
    assert (
        throt_db.increment(
            "rid", b"pid", throt_db.get("rid", b"pid", lock=False)
        ).day_cnt
        == 1
    )


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


def test_locking():
    pr1 = ProfileThrottleRule({"per_day": 10, "persistent": True, "rule_id": "rid"})
    pr2 = ProfileThrottleRule({"per_day": 10, "persistent": True, "rule_id": "rid"})
    assert pr1.db.lock_value != pr2.db.lock_value  # Sanity check

    assert pr1._approve_profile_request(b"pid")
    assert not pr2._approve_profile_request(b"pid"), "Expected DB to be locked"
    with pytest.raises(RuntimeError):
        pr2._use_quota(b"pid")
    pr1._use_quota(b"pid")  # Clears lock
    assert pr2._approve_profile_request(b"pid")
    pr2._use_quota(b"pid")  # Clears lock to stop interference with other tests


def test_explicit_locking(db_uri):
    db1 = ProfileThrottleDb({"persistent": True, "db-uri": db_uri, "rule_id": "rid"})
    db2 = ProfileThrottleDb({"persistent": True, "db-uri": db_uri, "rule_id": "rid"})
    prof_cnt1 = db1.get("rid", b"pid", lock=False)
    prof_cnt2 = db2.get("rid", b"pid", lock=False)
    assert not db1.is_locked(prof_cnt1)
    assert not db2.is_locked(prof_cnt2)
    db1.lock("rid", b"pid", prof_cnt1)
    prof_cnt1 = db1.get("rid", b"pid", lock=False)
    prof_cnt2 = db2.get("rid", b"pid", lock=False)
    assert not db1.is_locked(prof_cnt1)
    assert db2.is_locked(prof_cnt2)
    db1.unlock("rid", b"pid", prof_cnt1)
    prof_cnt1 = db1.get("rid", b"pid", lock=False)
    prof_cnt2 = db2.get("rid", b"pid", lock=False)
    assert not db1.is_locked(prof_cnt1)
    assert not db2.is_locked(prof_cnt2)


def test_locking_timeout():
    expiry_secs = 3

    pr1 = ProfileThrottleRule(
        {
            "per_day": 10,
            "persistent": True,
            "rule_id": "rid",
            "expiry_secs": expiry_secs,
        }
    )
    pr2 = ProfileThrottleRule(
        {
            "per_day": 10,
            "persistent": True,
            "rule_id": "rid",
            "expiry_secs": expiry_secs,
        }
    )
    assert pr1.db.lock_value != pr2.db.lock_value  # Sanity check

    assert pr1._approve_profile_request(b"pid")
    assert not pr2._approve_profile_request(b"pid"), "Expected DB to be locked"

    time.sleep(expiry_secs)
    assert pr2._approve_profile_request(b"pid"), "Expected lock to have expired"
    pr2._use_quota(b"pid")  # Clears lock to stop interference with other tests
