# SPDX-FileCopyrightText: © Atakama, Inc <support@atakama.com>
# SPDX-License-Identifier: LGPL-3.0-or-later

"""
A collection of rule plugins that allow basic policies to be implemented when using
the Atakama Rule Engine.

Time ranges, quotas, and other simple checks are implemented.

For more complex policies, a custom plugin can be built and loaded into the keyserver,
see https://github.com/AtakamaLLC/atakama_sdk.

## Example policy
```
decrypt:
  -  - rule: time-range-rule
       time_start: 8:00am
       time_end: 6:00pm
     - rule: per-profile-throttle-rule
       per_day: 30
       persistent: True

  -  - rule: meta-rule
       paths:
        - /public

search:
  -  - rule: profile-id-rule
       profile_ids:
         - humble busy much cactus

  -  - rule: per-profile-throttle-rule
       per_hour: 20
       per_day: 100
       persistent: True
```
In this policy, decryption requests could be approved via one of two rule sets. In the first,
if the time is between 8am and 6pm, each profile may decrypt 30 files per day. In the second, if the
authenticated metadata for the file being decrypted starts with "/public", then the
decryption will be approved.

Search requests also have two ways to be approved. If the requesting profile matches the
words "humble busy much cactus", then search requests are approved unrestricted. Any other
profile would hit the second rule set, allowing 20 searches per hour and 100 per day.
"""
from .time_range import TimeRangeRule
from .per_profile_throttle import ProfileThrottleRule
from .profile_id import ProfileIdRule
from .meta_str import MetaRule
from .session_params import SessionParamsRule
