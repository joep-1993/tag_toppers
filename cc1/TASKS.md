# TASKS
_Active task tracking. Update when: starting work, completing tasks, finding blockers._

## Current Sprint
_Active tasks for immediate work_

## In Progress
_Tasks currently being worked on_

## Completed
_Finished tasks (move here when done)_

- [x] Fix listing tree to handle Custom Label VALUE units - extended tree conversion to handle ALL positive Custom Label units (not just OTHERS), enabling Item-ID exclusions for value-based label structures #claude-session:2025-10-31
- [x] Improve LISTING_GROUP_ALREADY_EXISTS error handling - treat duplicate listing errors as non-critical warnings #claude-session:2025-10-30
- [x] Fix tag_toppers campaign tree processing - skip tag_toppers campaigns in label-based tree logic #claude-session:2025-10-30
- [x] Fix CANNOT_SET_BIDS_ON_LISTING_GROUP_SUBDIVISION error - bids now only set on UNIT nodes #claude-session:2025-10-30
- [x] Fix authentication and credential loading - updated to read all credentials from creds file #claude-session:2025-10-30
- [x] Fix multiple subdivision tree rebuild overwriting issue - batch atomic rebuild #claude-session:2025-10-30
- [x] Fix Item-ID OTHERS detection for multi-label trees #claude-session:2025-10-30
- [x] Fix custom label exclusion preservation in listing tree rebuild #claude-session:2025-10-29
- [x] Fix listing tree rebuild logic to prevent LISTING_GROUP_ALREADY_EXISTS errors #claude-session:2025-10-28
- [x] Add promo exclusion detection and conditional preservation #claude-session:2025-10-28
- [x] Fix Proto-plus WhichOneof attribute access errors #claude-session:2025-10-28
- [x] Add Item-ID exclusion visibility with print statements #claude-session:2025-10-28
- [x] Implement spreadsheet update function to mark processed rows #claude-session:2025-10-28
- [x] Add sleep delays to prevent concurrent modification errors #claude-session:2025-10-28
- [x] Initialize CC1 documentation system #claude-session:2025-10-17

## Blocked
_Tasks waiting on dependencies_

---

## Task Tags Guide
- `#priority:` high | medium | low
- `#estimate:` estimated hours (1h, 2h, etc.)
- `#blocked-by:` what's blocking this task
- `#claude-session:` date when Claude worked on this
- `#needs:` what resources/decisions are needed
