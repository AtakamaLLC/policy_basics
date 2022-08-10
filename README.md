# policy\_basics

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



# [policy\_basics](#policy_basics).meta_str


## MetaRule(RulePlugin)

Basic rule for exact match of profile ids:

YML Arguments:
 - paths:
    - list of paths
 - regexes:
    - list of regexes
 - case_sensitive: true or false
 - require_complete: require paths to have complete, validated metadata
```
Example:
    - rule: meta-rule
      paths:
        - /startswith/hr
        - contains/subpath
        - anysubpath/
        - basename
        - basename.with_ext
```

All paths and regex's that start with an '!' are inverted (not-match)
    - paths cannot match any 'inverted'

Regex matches are python (PCRE) standard regular expressions.

Path matches use the following rules:
 - paths can contain wildcards "*", that won't pass path-component boundaries
 - paths that don't contain a "/" are assumed to be file-basename matches
 - paths that contain a "/" are assumed to be path-component matches
 - paths that don't start with "/" are assumed to be subpath matches (match anywhere)




# [policy\_basics](#policy_basics).per_profile_throttle


## ProfileThrottleRule(RulePlugin)

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




# [policy\_basics](#policy_basics).profile_id


## ProfileIdRule(RulePlugin)

Basic rule for exact match of profile ids:

YML Arguments:
 - profile_ids:
    - profile_id_in_hex
    - profile words space delimited

```
Example:
    - rule: profile-id-rule
      profile_ids:
        - d56e89af673fe1897fdcc8
        - correct horse battery staple diamond hands
```




# [policy\_basics](#policy_basics).session_params


## SessionParamsRule(RulePlugin)

Container rule for session parameters.

YML Arguments:
 - max_request_count: int
 - max_time_seconds: int
 - end_by_time: HH:MM[am|pm] [TZ]

Default is no maximum requests, 5 minute session.

```
Example:
    - rule: session-params-rule
    - max_request_count: 100
    - max_time_seconds: 28800
    - end_by_time: 5:00pm EST
```
```




# [policy\_basics](#policy_basics).time_range


## TimeRangeRule(RulePlugin)

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




