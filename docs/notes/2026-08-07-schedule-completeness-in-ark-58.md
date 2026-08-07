# Schedule completeness stays inside ARK-58

Status: **accepted**

ARK-58 found that schedule v1 could not distinguish a sourced market closure
from a missing trading session because both appeared as an absent date. The
owner approved a strict pre-lease completeness check, then chose to keep that
work inside ARK-58 rather than add another Sprint 1 task.

The smallest safe change is a versioned schedule v2 that keeps the existing
content-addressed schedule boundary and adds explicit closure dates with source
reasons. Every date in a requested full closed month must be either a session or
a closure. Schedule v1 remains readable for old evidence but cannot start a new
ARK-58 run. Incomplete evidence fails before lease, storage, credentials, or an
Upstox request. The tool does not guess exchange holidays.

ARK-65 was canceled without code, commit, or push. Its separate draft and branch
were removed; this note preserves the useful decision without increasing the
Sprint 1 task count.
