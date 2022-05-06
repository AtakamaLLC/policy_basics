# SPDX-FileCopyrightText: © Atakama, Inc <support@atakama.com>
# SPDX-License-Identifier: LGPL-3.0-or-later

import os
import json
import time
from datetime import datetime
from threading import RLock

import logging
from atakama import RulePlugin, ApprovalRequest, ProfileInfo

from policy_basics.simple_db import AbstractDb, FileDb, MemoryDb

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

LOCAL_TIMEZONE = datetime.now().astimezone().tzinfo

INFINITE = -1


class Timer:
    @staticmethod
    def now():
        return datetime.now(LOCAL_TIMEZONE)

    @staticmethod
    def time():
        return time.time()


class ProfileCount:
    hour_cnt: int = 0
    day_cnt: int = 0

    def __init__(self, timestamp=None, hour_cnt=0, day_cnt=0):
        if timestamp and (hour_cnt or day_cnt):
            now = Timer.now()
            reqtime = datetime.fromtimestamp(timestamp, LOCAL_TIMEZONE)

            reqdate = reqtime.date()
            today = now.date()
            if today != reqdate:
                day_cnt = 0
                hour_cnt = 0
            else:
                reqhour = reqtime.hour
                curhour = now.hour
                if reqhour != curhour:
                    hour_cnt = 0

        self._ts = Timer.time()
        self.hour_cnt = int(hour_cnt)
        self.day_cnt = int(day_cnt)

    @staticmethod
    def from_dict(dat):
        return ProfileCount(dat["tm"], dat["hr"], dat["dy"])

    @staticmethod
    def from_str(dat: str):
        return ProfileCount.from_dict(json.loads(dat))

    def to_dict(self):
        return {"tm": self._ts, "hr": self.hour_cnt, "dy": self.day_cnt}

    def to_str(self) -> str:
        return self._dict_to_str(self.to_dict())

    @staticmethod
    def _dict_to_str(dct) -> str:
        return json.dumps(dct)

    def increment(self):
        self.hour_cnt += 1
        self.day_cnt += 1


class ProfileThrottleDb:
    db: AbstractDb

    def __init__(self, args):
        if not args.get("persistent", False):
            self.db = MemoryDb()
        else:
            path = str(args.get("db-file", os.path.expanduser("~/profile-throttle.db")))
            try:
                self.db = FileDb(path)
            except Exception as ex:  # pylint: disable=broad-except
                # deal with corruption by recovering
                log.error("unable to open %s: %s", path, repr(ex))
                # save the old one, maybe for debugging or something
                os.replace(path, path + ".old")
                self.db = FileDb(path)

    @staticmethod
    def _get_db_key(rule_id: str, profile_id: bytes):
        return profile_id.hex() + ":" + rule_id

    def get(self, rule_id: str, profile_id: bytes) -> ProfileCount:
        data = self.db.get(self._get_db_key(rule_id, profile_id))
        if not data:
            return ProfileCount()
        try:
            return ProfileCount.from_str(data)
        except (ValueError, TypeError, AssertionError, KeyError):
            log.warning("invalid value in db, resetting: (%s)", data)
            return ProfileCount()

    def increment(self, rule_id: str, profile_id: bytes, pc: ProfileCount):
        pc.increment()
        self.db.set(self._get_db_key(rule_id, profile_id), pc.to_str())
        return pc

    def clear(self, rule_id: str, profile_id: bytes):
        self.db.remove(self._get_db_key(rule_id, profile_id))


class ProfileThrottleRule(RulePlugin):
    """
    Basic rule for per-profile limits:

    YML Arguments:
     - per_hour: requests per hour
     - per_day: requests per day
     - persistent: restarting the server not clear current quotas

    ```
    Example:
        - rule: per-profile-throttle-rule
          per_hour: 10
          per_day: 100
          persistent: False
    ```

    Request data are stored per-rule. If there are 2 throttle rules which may match a profile,
    each will record its own request counts for that profile, i.e. the limits are additive.
    """

    @staticmethod
    def name() -> str:
        return "per-profile-throttle-rule"

    def __init__(self, args):
        super().__init__(args)
        self.per_hour = args.get("per_hour", INFINITE)
        self.per_day = args.get("per_day", INFINITE)
        self.db = ProfileThrottleDb(args)

    def approve_request(self, request: ApprovalRequest):
        return self._approve_profile_request(request.profile.profile_id)

    def _approve_profile_request(self, profile_id):
        pc = self.db.get(self.rule_id, profile_id)
        within = self._within_quota(pc)
        log.debug(
            "ProfileThrottleRule._approve_profile_request rule_id=%s within=%s "
            "day_cnt=%i hour_cnt=%i",
            self.rule_id,
            within,
            pc.day_cnt,
            pc.hour_cnt,
        )
        return within

    def use_quota(self, request: ApprovalRequest):
        return self._use_quota(request.profile.profile_id)

    def _use_quota(self, profile_id):
        pc = self.db.get(self.rule_id, profile_id)
        pc = self.db.increment(self.rule_id, profile_id, pc)
        log.debug(
            "ProfileThrottleRule._use_quota rule_id=%s now " "day_cnt=%i hour_cnt=%i",
            self.rule_id,
            pc.day_cnt,
            pc.hour_cnt,
        )

    def _approve_and_use_quota(self, profile_id):
        # For tests
        if self._approve_profile_request(profile_id):
            self._use_quota(profile_id)
            return True
        return False

    def _within_quota(self, pc):
        return (self.per_day == INFINITE or pc.day_cnt < self.per_day) and (
            self.per_hour == INFINITE or pc.hour_cnt < self.per_hour
        )

    def clear_quota(self, profile: ProfileInfo) -> None:
        self.db.clear(self.rule_id, profile.profile_id)

    def at_quota(self, profile: ProfileInfo) -> bool:
        pc = self.db.get(self.rule_id, profile.profile_id)
        return not self._within_quota(pc)
