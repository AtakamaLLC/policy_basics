# pylint: disable=invalid-name
import unittest.mock
import dateutil.parser
import pytest

from atakama import ApprovalRequest, RequestType, ProfileInfo

from policy_basics import TimeRangeRule
from policy_basics.time_range import LOCAL_TIMEZONE


def test_time_range():
    tr = TimeRangeRule(
        {
            "days": [1, 2, 3],
            "include": ["2022-03-07"],
            "exclude": ["2022-03-08"],
            "time_start": "09:00+04:00",
            "time_end": "17:00+04:00",
            "rule_id": "rid",
        }
    )

    # include
    assert tr.times.in_range(dateutil.parser.parse("2022-03-07 09:00+04:00"))
    # timezone
    assert not tr.times.in_range(dateutil.parser.parse("2022-03-07 09:00+05:00"))
    # exclude
    assert not tr.times.in_range(dateutil.parser.parse("2022-03-08 09:00+04:00"))
    # wednesday
    assert tr.times.in_range(dateutil.parser.parse("2022-03-09 09:00+04:00"))
    # just in time
    assert tr.times.in_range(dateutil.parser.parse("2022-03-09 17:00+04:00"))
    # too late
    assert not tr.times.in_range(dateutil.parser.parse("2022-03-09 18:00+04:00"))

    # interface is cool
    with unittest.mock.patch("policy_basics.time_range.datetime") as dt:
        dt.now.return_value = dateutil.parser.parse("2022-03-09 17:00+04:00")
        assert tr.approve_request(
            ApprovalRequest(
                request_type=RequestType.DECRYPT,
                device_id=b"did",
                profile=ProfileInfo(b"pi", profile_words=[]),
                auth_meta=[],
                cryptographic_id=None,
            )
        )
    # check if there are bugs when we're not mocked
    tr.approve_request(
        ApprovalRequest(
            request_type=RequestType.DECRYPT,
            device_id=b"did",
            profile=ProfileInfo(b"pi", profile_words=[]),
            auth_meta=[],
            cryptographic_id=None,
        )
    )


def test_tz_default():
    tr = TimeRangeRule({"time_start": "09:00", "time_end": "17:00", "rule_id": "rid"})
    assert tr.times.time_of_day_start.tzinfo
    assert tr.times.time_of_day_end.tzinfo


def test_day_only():
    tr = TimeRangeRule(
        {
            "days": [1, 2, 3],
            "rule_id": "rid",
        }
    )
    assert not tr.times.in_range(dateutil.parser.parse("2022-03-07 19:00+04:00"))
    assert tr.times.in_range(dateutil.parser.parse("2022-03-08 01:00+04:00"))


def local_parse(s):
    return dateutil.parser.parse(s).replace(tzinfo=LOCAL_TIMEZONE)


def test_time_only():
    tr = TimeRangeRule(
        {
            "time_start": "09:00am",
            "time_end": "09:00pm",
            "rule_id": "rid",
        }
    )
    assert tr.times.in_range(local_parse("2022-03-07 09:00am"))
    assert tr.times.in_range(local_parse("2022-03-07 09:00pm"))
    assert not tr.times.in_range(local_parse("2022-03-07 10:00pm"))


def test_assertions():
    TimeRangeRule(
        {
            "days": [1, 2, 3],
            "include": ["2022-03-07"],
            "exclude": ["2022-03-08"],
            "time_start": "09:00+04:00",
            "time_end": "17:00+04:00",
            "rule_id": "rid",
        }
    )

    with pytest.raises(Exception):
        TimeRangeRule(
            {
                "days": [7],
                "rule_id": "rid",
            }
        )

    with pytest.raises(Exception):
        TimeRangeRule(
            {
                "include": ["2022-03-07"],
                "exclude": ["2022-03-07"],
                "rule_id": "rid",
            }
        )

    with pytest.raises(Exception):
        TimeRangeRule(
            {
                "time_end": "09:00+04:00",
                "time_start": "17:00+04:00",
                "rule_id": "rid",
            }
        )

    with pytest.raises(Exception):
        TimeRangeRule(
            {
                "time_start": "09:00+04:00",
                "rule_id": "rid",
            }
        )

    with pytest.raises(Exception):
        TimeRangeRule(
            {
                "time_end": "17:00+04:00",
                "rule_id": "rid",
            }
        )
