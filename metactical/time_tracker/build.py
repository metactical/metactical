"""The build this code is. Bump BUILD and add a CHANGELOG.md entry with every update (see CHANGELOG.md).

Shown at the bottom of the Time Clock and returned by `get_my_permissions`, so anyone can say which build they are on
and we can go back to a previous one: `git checkout tt-build-<N>`, redeploy, migrate (read that build's rollback notes).
"""

BUILD = 7
BUILD_DATE = "2026-10-06"
