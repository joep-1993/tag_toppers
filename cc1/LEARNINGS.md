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

##### Item-ID OTHERS Detection in Multi-Label Trees (2025-10-30)
- **Problem**: LISTING_GROUP_ALREADY_EXISTS error when adding Item-ID OTHERS to multi-label trees
- **Root Cause**: Item-ID OTHERS in multi-label structures appear as POSITIVE UNITS with no case_value (query shows dimension as "ROOT")
- **Solution**: Detect both explicit Item-ID OTHERS and POSITIVE UNITS with no case_value
- **Detection Pattern**:
  ```python
  # Check for explicit Item-ID OTHERS
  if dim_type == "product_item_id":
      item_id_value = case_val.product_item_id.value
      if not item_id_value:
          has_item_id_others = True

  # Also check for POSITIVE UNITS with no case_value (ROOT dimension)
  else:
      # No case_value - this is likely an OTHERS case
      if child_node['type'] == 'UNIT' and not child_node['negative']:
          # This is an OTHERS unit (Item-ID OTHERS most likely)
          has_item_id_others = True
  ```
- **Key Insight**: Multi-label trees represent Item-ID OTHERS differently than single-label trees

##### Terminal Subdivision Detection (2025-10-30)
- **Purpose**: Find where to add Item-ID exclusions in complex multi-label tree structures
- **Pattern**: Identify subdivisions with UNIT children but no SUBDIVISION children (terminal subdivisions)
- **Algorithm**:
  ```python
  # Find subdivisions that should have Item-ID children
  for sub_res in subdivision_nodes:
      children = tree_map[sub_res]['children']
      if not children:
          # No children - this is a leaf subdivision
          target_subdivisions.append(sub_res)
      else:
          # Has UNIT children but no SUBDIVISION children
          has_unit_children = any(tree_map[child]['type'] == 'UNIT' for child in children)
          has_subdivision_children = any(tree_map[child]['type'] == 'SUBDIVISION' for child in children)
          if has_unit_children and not has_subdivision_children:
              target_subdivisions.append(sub_res)
  ```
- **Benefits**: Works universally for both single-label and multi-label tree patterns
- **Use Case**: Replaced "deepest level" detection which didn't work for all tree structures

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

##### Multi-Label Tree Testing (2025-10-30)
- **Test Strategy**: Test on real multi-label tree with existing Item-ID OTHERS
- **Test Case**: Ad group 167597626207 in campaign 21411963098 (customer 7938980174)
- **Initial Structure**: 3 label subdivisions (no data, nd_c, nd_cr) each with:
  - 1 POSITIVE UNIT with "ROOT" dimension (Item-ID OTHERS with 0.10€ bid)
  - 1 Item-ID exclusion
- **Test**: Add 3 new test Item-ID exclusions to verify no LISTING_GROUP_ALREADY_EXISTS error
- **Result**: Successfully added 9 exclusions total (3 to each subdivision) without errors
- **Verification**: Tree grew from 11 to 20 nodes, all Item-ID OTHERS correctly detected and preserved

##### Atomic Tree Rebuild Problem (2025-10-30)
- **Problem**: When multiple subdivisions need UNIT-to-SUBDIVISION conversion, processing them sequentially causes each rebuild to overwrite previous changes
- **Root Cause**: `_convert_unit_to_subdivision_atomic()` removes ENTIRE tree (all nodes) and recreates from scratch. Second rebuild overwrites first rebuild's changes.
- **Example**: 3 subdivisions needing conversion:
  - Rebuild 1: Removes 14 nodes, creates 175 nodes (subdivision 1 has Item-IDs) ✓
  - Rebuild 2: Removes 175 nodes, creates 175 nodes (subdivision 2 has Item-IDs, subdivision 1 LOST) ✗
  - Rebuild 3: Fails with CONCURRENT_MODIFICATION error
  - Result: Only subdivision 2 has Item-IDs, subdivisions 1 and 3 are missing them
- **Solution**: Collect all subdivisions needing conversion in first pass, then process ALL in single tree rebuild
- **Implementation**: Two-pass approach:
  ```python
  # FIRST PASS: Collect all targets
  subdivisions_needing_rebuild = []
  for sub_res_name in target_subdivisions:
      if needs_rebuild(sub_res_name):
          subdivisions_needing_rebuild.append({
              'res_name': sub_res_name,
              'non_item_id_others_unit': unit_data,
              'children': children
          })

  # SECOND PASS: Single atomic rebuild for all
  if subdivisions_needing_rebuild:
      _convert_unit_to_subdivision_atomic(
          client, customer_id, ad_group_id, agc_service,
          subdivisions_needing_rebuild,  # Pass ALL targets
          unique_item_ids, default_bid_micros,
          tree_map, custom_label_structures
      )
  ```
- **Code Locations**: listing_tree.py:200-273 (collection), listing_tree.py:678-942 (atomic rebuild)

### Batch Tree Operations Pattern (2025-10-30)
- **Pattern**: When modifying multiple nodes requiring tree rebuild, collect all targets first, then apply all changes in single atomic operation
- **Why Needed**: Sequential tree rebuilds overwrite each other because each rebuild removes+recreates entire tree
- **Benefits**:
  - Prevents data loss from sequential rebuilds
  - More efficient (single API operation instead of multiple)
  - Avoids CONCURRENT_MODIFICATION errors
- **Use Cases**:
  - Adding Item-ID level to multiple subdivisions simultaneously
  - Bulk tree structure modifications
  - Any operation requiring multiple UNIT-to-SUBDIVISION conversions
- **Anti-Pattern**: Processing targets in loop with individual tree rebuilds

##### Invalid Case Value Fallback (2025-10-30)
- **Problem**: Nodes with missing or invalid case_value cause validation errors during tree rebuild
- **Symptom**: Nodes show as "ROOT" dimension in queries but have no actual case_value set
- **Solution**: Added fallback to detect and fix nodes without case_value:
  ```python
  # Detect nodes with no case_value
  elif not node.get('case_value'):
      # Set Item-ID OTHERS as fallback to avoid validation error
      empty_item_id = client.get_type("ProductItemIdInfo")
      criterion.listing_group.case_value.product_item_id._pb.MergeFrom(empty_item_id._pb)
      print(f"⚠️ WARNING: Node {node['temp_id']} has no case_value, defaulting to Item-ID OTHERS")
  ```
- **Code Location**: listing_tree.py:950-961
- **Prevention**: This handles corrupted tree data gracefully during rebuild

##### Credential Loading from File (2025-10-30)
- **Problem**: `ValueError: The specified login customer ID is invalid` - environment variables not set in Windows environment
- **Root Cause**: Script only loaded CLIENT_ID and CLIENT_SECRET from creds file, other credentials required env vars
- **Solution**: Update credential loading to read all 5 required credentials from creds file:
  - GOOGLE_CLIENT_ID
  - GOOGLE_CLIENT_SECRET
  - GOOGLE_REFRESH_TOKEN
  - GOOGLE_DEVELOPER_TOKEN
  - GOOGLE_LOGIN_CUSTOMER_ID
- **Implementation**: Single `load_google_credentials()` function that tries env vars first, then reads from creds file
- **Code Location**: GSD_tagtoppers.py:36-80
- **Pattern**: Always provide file-based fallback for credentials in cross-platform environments

##### Bidding Restrictions (2025-10-30)
- **Error**: `CANNOT_SET_BIDS_ON_LISTING_GROUP_SUBDIVISION` - cannot set bids on subdivision nodes
- **Cause**: Google Ads API only allows bids on UNIT (leaf) nodes, not SUBDIVISION nodes
- **Solution**: Check node type before setting bid:
  ```python
  # Set bid (only for UNIT nodes - subdivisions cannot have bids)
  if node.get('bid_micros') and node['type'] == 'UNIT':
      criterion.cpc_bid_micros = node['bid_micros']
  ```
- **Code Location**: listing_tree.py:938-940
- **Key Rule**: Never attempt to set `cpc_bid_micros` on SUBDIVISION nodes

##### Campaign Structure Types (2025-10-30)
- **Two Tree Structures**: Tag_toppers campaigns use different tree structure than label-based campaigns
- **Label-Based Campaigns**: Use EXCLUSION logic (block specific Item-IDs from showing)
  - Labels: a, b, c, no data, no ean
  - Function: `rebuild_tree_with_label_and_item_ids()`
  - Structure: Custom Label subdivisions → Item-ID OTHERS (positive) + Item-ID exclusions (negative)
- **Tag_Toppers Campaigns**: Use INCLUSION logic (only show specific Item-IDs)
  - Label: tag_toppers
  - Function: `rebuild_tree_with_specific_item_ids()`
  - Structure: Root → Item-ID OTHERS (negative) + Specific Item-IDs (positive)
- **Important**: Never apply label-based tree logic to tag_toppers campaigns and vice versa
- **Detection**: Check campaign name for 'label:tag_toppers' to determine structure type
- **Code Location**: GSD_tagtoppers.py:990-993

##### Non-Critical Error Handling (2025-10-30)
- **Pattern**: Distinguish between critical and non-critical Google Ads API errors
- **Use Case**: `LISTING_GROUP_ALREADY_EXISTS` errors should not prevent marking rows as processed
- **Implementation**:
  ```python
  except GoogleAdsException as ex:
      is_duplicate_error = any(
          hasattr(e.error_code, 'criterion_error') and
          e.error_code.criterion_error.name == 'LISTING_GROUP_ALREADY_EXISTS'
          for e in ex.failure.errors
      )
      if is_duplicate_error:
          print(f"⚠️ Warning: Some listings already exist (non-critical)")
          # Continue as success
      else:
          print(f"❌ Error: {ex.failure}")
          row_processed_successfully = False
  ```
- **Code Location**: GSD_tagtoppers.py:1006-1016, 1030-1040
- **Benefits**: Allows script to handle idempotency gracefully

##### Custom Label Unit Conversion (2025-10-31)
- **Problem**: Script only converted Custom Label OTHERS units to subdivisions, failed on VALUE units (e.g., label="b")
- **Symptom**: `LISTING_GROUP_REQUIRES_SAME_DIMENSION_TYPE_AS_SIBLINGS` when trying to add Item-ID siblings to Custom Label siblings
- **Root Cause**: Detection logic only looked for OTHERS units (`if not attr_value`), missed positive units with values
- **Solution**: Collect ALL positive (non-negative) Custom Label units for conversion:
  ```python
  # Collect POSITIVE (non-negative) units for conversion
  # This includes both OTHERS and VALUE units
  if not child_node['negative']:
      positive_non_item_id_units.append({
          'res_name': child_res,
          'case_value': case_val,
          'bid_micros': child_node['bid_micros']
      })
  ```
- **Conversion Process**: Each positive unit → SUBDIVISION with Item-ID OTHERS + Item-ID exclusions as children
- **Example**: Label "b" UNIT → Label "b" SUBDIVISION → [Item-ID OTHERS, Item-ID exclusions...]
- **Code Location**: listing_tree.py:233-240 (detection), 757-807 (conversion)
- **Key Insight**: ALL positive Custom Label units need Item-ID level, not just OTHERS units
