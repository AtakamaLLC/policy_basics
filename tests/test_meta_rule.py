# SPDX-FileCopyrightText: © Atakama, Inc <support@atakama.com>
# SPDX-License-Identifier: LGPL-3.0-or-later

from atakama import ApprovalRequest, MetaInfo

from policy_basics.meta_str import MetaRule


def meta(*paths, complete=True):
    return ApprovalRequest(
        request_type=None,
        device_id=b"whatever",
        profile=None,
        auth_meta=[MetaInfo(p, complete) for p in paths],
        cryptographic_id=b"cid",
    )


def test_subdir():
    pr = MetaRule(
        {
            "paths": ["/root/sub"],
            "rule_id": "rid",
        }
    )
    assert pr.approve_request(meta("root/sub/path/basename.ext"))
    assert not pr.approve_request(meta("root/other/sub/basename.ext"))
    assert not pr.approve_request(meta("root/subxx/path/basename.ext"))
    assert not pr.approve_request(meta("root/xxsub/path/basename.ext"))
    assert not pr.approve_request(meta("rooty/sub/path/basename.ext"))


def test_paths():
    pr = MetaRule(
        {
            "paths": ["sub/path", "/root/sub", "*.ext", "basename.*", "baseonly"],
            "rule_id": "rid",
        }
    )
    assert pr.approve_request(meta("root/sub/path/basename.ext"))
    assert pr.approve_request(meta("root/sub/path/otherfile.whatever"))
    assert not pr.approve_request(meta("root/subxx/path/otherfile.whatever"))
    assert pr.approve_request(meta("whatever.ext"))
    assert pr.approve_request(meta("root/sub/xxx"))
    assert pr.approve_request(meta("sdfjksdfjk/sub/path/sdfsdfj"))
    assert pr.approve_request(meta("basename.xxx"))
    # insensitive
    assert pr.approve_request(meta("Root/Sub/Path/Basename.ext"))
    assert pr.approve_request(meta("wherever/Basename.anyext"))
    assert pr.approve_request(meta("wherever/anyfile.ext"))
    assert pr.approve_request(meta("wherever/baseonly"))
    assert not pr.approve_request(meta("root/sub/path/basename.ext", "some/other"))
    # sub paths must be sub paths
    assert not pr.approve_request(meta("sub/path", complete=False))
    assert not pr.approve_request(meta("sub/path.txt"))
    assert pr.approve_request(meta("sub/path"))
    # sub is ok
    assert pr.approve_request(meta("some/sub/path", complete=False))


def test_extra_slashes():
    pr = MetaRule(
        {
            "paths": ["/sub/"],
            "rule_id": "rid",
        }
    )
    assert pr.approve_request(meta("sub/file"))
    assert pr.approve_request(meta("sub/two/file"))
    assert not pr.approve_request(meta("sub2/file"))


def test_glob_basename():
    pr = MetaRule({"paths": ["basename.*"], "rule_id": "rid"})
    assert pr.approve_request(meta("basename.xxx"))
    assert pr.approve_request(meta("basename.xxx"))
    assert not pr.approve_request(meta("basename/xxx"))
    assert not pr.approve_request(meta("basename.xxx/yyy"))
    assert not pr.approve_request(meta("basename.xxx/"))


def test_glob_subcomponent():
    pr = MetaRule({"paths": ["sub/co*mp"], "rule_id": "rid"})
    assert pr.approve_request(meta("root/sub/comp/basename"))
    assert pr.approve_request(meta("root/sub/co77mp/basename"))
    assert not pr.approve_request(meta("root/sub/co/mp/basename"))

    pr = MetaRule({"paths": ["little*sub/"], "rule_id": "rid"})
    assert not pr.approve_request(meta("root/little sub"))
    assert pr.approve_request(meta("root/little sub/"))
    assert pr.approve_request(meta("root/little sub/comp/basename"))
    assert pr.approve_request(meta("root/littlesub/comp/basename"))
    assert pr.approve_request(meta("root/littlesub/comp/basename"))
    assert not pr.approve_request(meta("root/little/sub"))

    pr = MetaRule({"paths": ["little*sub/x"], "rule_id": "rid"})
    assert pr.approve_request(meta("root/little sub/x"))
    assert pr.approve_request(meta("root/little sub/x/y"))
    assert not pr.approve_request(meta("root/little sub/xzz"))
    assert not pr.approve_request(meta("root/little sub/xzz/y"))


def test_sensitive_paths():
    pr = MetaRule(
        {
            "paths": ["sub/path", "/root/sub", "*.ext", "basename.*"],
            "case_sensitive": True,
            "rule_id": "rid",
        }
    )
    assert pr.approve_request(meta("root/sub/path/basename.ext"))
    assert not pr.approve_request(meta("Root/Sub/Path/Basename.Ext"))


def test_meta_regex():
    pr = MetaRule({"regexes": ["reg.*ex"], "rule_id": "rid"})
    assert pr.approve_request(meta("reg777ex"))


def test_meta_invert():
    pr = MetaRule({"regexes": ["!regex"], "rule_id": "rid"})
    assert pr.approve_request(meta("nomatch"))
    assert not pr.approve_request(meta("regex"))
    pr = MetaRule({"paths": ["!sub/path"], "rule_id": "rid"})
    assert pr.approve_request(meta("anywhere/else"))
    assert not pr.approve_request(meta("root/sub/path"))
    assert pr.approve_request(meta("sub/path.txt"))
    assert not pr.approve_request(meta("sub/path"))
    pr = MetaRule({"paths": ["!/taxi", "/tax*"], "rule_id": "rid"})
    assert pr.approve_request(meta("taxes"))
    assert not pr.approve_request(meta("taxi"))


def test_require_complete():
    pr = MetaRule(
        {
            "paths": ["sub/path", "/root/sub", "*.ext", "basename.*"],
            "require_complete": True,
            "rule_id": "rid",
        }
    )
    assert not pr.approve_request(meta("root/sub/path/basename.ext", complete=False))
    assert pr.approve_request(meta("root/sub/path/basename.ext", complete=True))
