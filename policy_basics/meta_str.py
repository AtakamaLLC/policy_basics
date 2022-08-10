# SPDX-FileCopyrightText: © Atakama, Inc <support@atakama.com>
# SPDX-License-Identifier: LGPL-3.0-or-later

import re
from typing import Optional, List, Tuple, Pattern

from atakama import RulePlugin, ApprovalRequest

MINIMUM_WORD_COUNT = 4


class MetaRule(RulePlugin):
    """
    Basic rule for exact match of file paths:

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
    """

    @staticmethod
    def name() -> str:
        return "meta-rule"

    def __precomp(self, ent):
        flags = 0
        if not self.__sensitive:
            flags = re.I

        invert = False
        if ent[0] == "!":
            ent = ent[1:]
            invert = True
        return invert, flags, ent

    def __comp_path(self, path) -> Tuple[Pattern, bool]:
        invert, flags, path = self.__precomp(path)
        if path[0] == "*":
            path = re.escape(path[1:])
            path = path.replace("\\*", "[^/]*")
            regex = f".*{path}"
        elif path[0] == "/":
            if path.endswith("/"):
                path = path.rstrip("/")
            path = re.escape(path)
            path = path.replace("\\*", "[^/]*")
            regex = f"^{path}/|^{path}$"
        elif "/" in path:
            path = re.escape(path)
            path = path.replace("\\*", "[^/]*")
            if not path.endswith("/"):
                # match full component or ends-with
                regex = f"\\/{path}/|\\/{path}$"
            else:
                # match full component only
                path = path.rstrip("/")
                regex = f"\\/{path}/"
        else:
            path = re.escape(path)
            path = path.replace("\\*", "[^/]*")
            regex = f"(\\/|^){path}$"

        comp = re.compile(regex, flags)

        return comp, invert

    def __comp_regex(self, regex):
        invert, flags, regex = self.__precomp(regex)

        comp = re.compile(regex, flags)

        return comp, invert

    def __init__(self, args):
        # partial strings can match or not, depending on whether they contain the necessary info
        self.__require_complete = args.get("require_complete", False)
        self.__sensitive = args.get("case_sensitive", False)
        self.__regexes: List[Tuple[Pattern, bool]] = []
        for regex in args.get("regexes", []):
            comp = self.__comp_regex(regex)
            self.__regexes.append(comp)

        for path in args.get("paths", []):
            comp = self.__comp_path(path)
            self.__regexes.append(comp)
        super().__init__(args)

    def approve_request(self, request: ApprovalRequest) -> Optional[bool]:
        has_meta = False
        for meta in request.auth_meta:
            if self.__require_complete and not meta.complete:
                return False
            should_approve = False
            has_meta = True

            norm = meta.meta
            if not self.__sensitive:
                norm = norm.lower()

            assert norm[0] != "/"
            if meta.complete:
                norm = "/" + norm

            for regex, invert in self.__regexes:
                res = regex.search(norm)
                if invert:
                    if res:
                        break
                    should_approve = True
                else:
                    if res:
                        should_approve = True
                        break

            if not should_approve:
                return False

        return has_meta
