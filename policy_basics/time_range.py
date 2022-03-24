import logging
from typing import Optional, Set, Iterable
from datetime import date, time, datetime

import dateutil.parser
from atakama import RulePlugin, ApprovalRequest

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

LOCAL_TIMEZONE = datetime.now().astimezone().tzinfo


class TimeArgs:
    # see https://docs.python.org/3/library/datetime.html#datetime.date.weekday
    ALL_DAYS: Set[int] = [0, 1, 2, 3, 4, 5, 6]

    def __init__(  # pylint: disable=too-many-arguments
        self,
        days: Iterable[int],
        include: Iterable[date],
        exclude: Iterable[date],
        time_start: Optional[time] = None,
        time_end: Optional[time] = None,
    ):
        self.days_of_week = set(days)
        self.include = set(include)
        self.exclude = set(exclude)
        self.time_of_day_start = time_start
        self.time_of_day_end = time_end
        assert not self.include.intersection(
            self.exclude
        ), "cannot have include and exclude of the same day"
        assert bool(time_start) == bool(
            time_end
        ), "must have both time start and end, or neither"
        assert not time_start or (
            time_start < time_end
        ), "time start must be less than time end"
        assert all(0 <= d <= 6 for d in self.days_of_week), "invalid day of week"

    def in_range(self, now: datetime):
        if now.date() in self.exclude:
            return False

        if now.date() not in self.include and now.weekday() not in self.days_of_week:
            return False

        if not (self.time_of_day_start and self.time_of_day_end):
            return True

        return self.time_of_day_start <= now.timetz() <= self.time_of_day_end

    @classmethod
    def from_dict(cls, args):
        return TimeArgs(
            days=args.get("days", cls.ALL_DAYS),
            include=cls.strs_to_dates(args.get("include", set())),
            exclude=cls.strs_to_dates(args.get("exclude", set())),
            time_start=cls.str_to_time(args.get("time_start", None)),
            time_end=cls.str_to_time(args.get("time_end", None)),
        )

    @staticmethod
    def strs_to_dates(strs: Iterable[str]):
        assert not isinstance(strs, str), "input must be iterable of str"
        return [dateutil.parser.parse(s).date() for s in strs]

    @staticmethod
    def str_to_time(tim: Optional[str]):
        if not tim:
            return None
        timetz = dateutil.parser.parse(tim).timetz()
        if not timetz.tzinfo:
            timetz = timetz.replace(tzinfo=LOCAL_TIMEZONE)
        return timetz


class TimeRangeRule(RulePlugin):
    """
    Basic rule for time ranges:

    YML Arguments:
     - time_start: time start (hh:mm)
     - time_end: time end (hh:mm)
     - days: list of days of the week, monday=0, default is 0-6
     - include: list of specific dates to include
     - exclude: list of specific dates to exclude

    ```
    Example:
        - rule: time-range-rule
          time_start: 9:00am
          time_end: 5:00pm
          exclude: 2022-06-01
    ```
    """

    @staticmethod
    def name() -> str:
        return "time-range-rule"

    def __init__(self, args):
        super().__init__(args)
        self.times = TimeArgs.from_dict(args)

    def approve_request(self, request: ApprovalRequest) -> Optional[bool]:
        now = datetime.now(tz=LOCAL_TIMEZONE)
        res = self.times.in_range(now)
        log.debug(
            "TimeRangeRule.approve_request rule_id=%s now=%s res=%s",
            self.rule_id,
            now,
            res,
        )
        return res
