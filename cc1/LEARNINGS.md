# LEARNINGS
_Capture mistakes, solutions, and patterns. Update when: errors occur, bugs are fixed, patterns emerge._

## Claude Code Patterns & Quirks
_Common misunderstandings and how to avoid them_

### Common Claude Misunderstandings
- **File Paths**: Use absolute paths when possible
- **Context Loss**: Claude doesn't remember previous sessions - always reference this file
- **Assumptions**: Claude may assume libraries are installed - always check first

### Commands That Work
```bash
# Python package installation
pip3 install --quiet google-ads google-api-python-client google-auth-httplib2 google-auth-oauthlib

# Google OAuth environment setup
export GOOGLE_CLIENT_ID="your-google-client-id"
export GOOGLE_CLIENT_SECRET="your-google-client-secret"
```

### Environment-Specific Quirks
_Document your environment setup and gotchas here_

---

## Project-Specific Patterns
_Add patterns and solutions as you discover them_

### Git Security
- **Credentials Management**: All credentials stored in `creds/` folder and excluded from git
- **File Exclusions**: `*.json` files are gitignored for security
- **Explicit Exclusions**: `credentials.json` and `gsd-campaign-creation.json` explicitly listed in .gitignore
- **Pattern**: Always verify sensitive folders are gitignored before committing

### Google Ads API Patterns
_Session: 2025-10-28_

#### Proto-Plus Wrapper Gotchas
- **WhichOneof Access**: Proto-plus wrapper requires `._pb.WhichOneof("dimension")` instead of `.WhichOneof("dimension")`
- **Error**: `AttributeError: Unknown field for ListingDimensionInfo: WhichOneof`
- **Solution**: Always use `case_val._pb.WhichOneof("dimension")` when checking dimension types

#### Concurrent Modification Prevention
- **Problem**: `CONCURRENT_MODIFICATION` errors when rebuilding listing trees
- **Cause**: Creating new tree immediately after deletion before API finishes processing
- **Solution**: Add `time.sleep(3)` after tree removal before rebuilding
- **Pattern**: Always wait 3+ seconds between delete and create operations on same resource

#### Listing Tree Management
- **LISTING_GROUP_ALREADY_EXISTS Error**: Attempting to add existing nodes incrementally
- **Solution**: Remove entire tree and rebuild from scratch when Item-ID exclusions exist
- **Pattern**: Use `safe_remove_entire_listing_tree()` + wait + `_create_standard_tree()` for reliability
- **Key Insight**: Tree rebuild is more reliable than incremental updates

##### Custom Label Exclusion Preservation (2025-10-29)
- **Problem**: Custom label exclusions were being removed when adding item ID exclusions
- **Root Cause**: Detection logic was treating NEGATIVE custom label units as requiring rebuild
- **Solution**: NEGATIVE custom label units are exclusions and should be preserved, not converted
- **Detection Pattern**: Only count POSITIVE non-item-ID units as requiring special handling
- **Code Pattern**:
  ```python
  # Only count POSITIVE (non-negative) units as needing special handling
  # NEGATIVE units are exclusions and should be left as siblings
  if child_node['type'] == 'UNIT' and not child_node['negative']:
      has_positive_non_item_id_unit_children = True
  ```

##### Tree Structure Simplification (2025-10-29)
- **Old Approach**: Created nested chain (INDEX1→INDEX2→INDEX3→INDEX4) for custom labels
- **Problem**: Complex structure, exclusions were lost during rebuild
- **New Approach**: Single subdivision at highest custom label index
- **Structure**:
  ```
  ROOT [SUBDIVISION]
  ├─ Custom Attr 0: OTHERS [NEGATIVE]
  └─ Custom Attr 0: <label> [SUBDIVISION]
     ├─ Custom Attr N: OTHERS [SUBDIVISION]  ← Highest index only
     │  ├─ Item ID: OTHERS [POSITIVE]
     │  └─ Item ID: excluded_items [NEGATIVE]
     ├─ Custom Attr 4: value1 [NEGATIVE]  ← Siblings to OTHERS
     └─ Custom Attr 4: value2 [NEGATIVE]
  ```
- **Key Insight**: Exclusions are siblings to OTHERS subdivision under label subdivision

#### Spreadsheet Updates
- **Service Account Permissions**: Need `https://www.googleapis.com/auth/spreadsheets` scope (not readonly)
- **Batch Updates**: Use `batchUpdate` API for efficient multi-row updates
- **Column G Pattern**: Track processed status in column G, only update rows that completed successfully
- **Error Handling**: Always include detailed error messages and traceback for Google Sheets API failures

#### Testing Patterns (2025-10-29)
##### Tree Preservation Testing
- **Test Strategy**: Reset tree → verify initial state → run rebuild → verify exclusions preserved
- **Test Case**: Ad group 144284844193 (customer 7938980174) with custom label 4 exclusions
- **Verification Steps**:
  1. Reset ad group tree to known state with custom label exclusions
  2. Query tree to document initial structure
  3. Run `rebuild_tree_with_label_and_item_ids()` with test item IDs
  4. Query tree again to verify both custom label and item ID exclusions exist
- **Expected Result**: Custom label exclusions preserved as siblings to item ID structure
- **Example**: Custom Label 4 exclusions ('8-13', '13-21') preserved alongside Item ID exclusions
