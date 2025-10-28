# Listing Tree Function - How It Works

## Overview
The `rebuild_tree_with_label_and_item_ids` function now properly handles all cases for adding Item-ID exclusions to existing Google Ads listing trees while respecting the API constraint that **all sibling nodes must use the same dimension type**.

## How It Works

### Step 1: Read Existing Tree
- Queries the Google Ads API to get the complete listing tree structure
- Builds a tree map with parent-child relationships
- Calculates depth for each node

### Step 2: Find Lowest Subdivisions
- Identifies all SUBDIVISION nodes at the deepest level
- These are the candidates for adding Item-ID exclusions

### Step 3: Process Each Subdivision (4 Cases)

#### Case 1: No Children ✅
**Scenario:** Subdivision has no children yet
```
└─ Custom Attr 1 OTHERS [SUBDIVISION] (no children)
```

**Action:** Directly add Item-ID structure:
```
└─ Custom Attr 1 OTHERS [SUBDIVISION]
   ├─ Item ID OTHERS [UNIT POSITIVE, €0.20]
   ├─ Item ID = 'id1' [UNIT NEGATIVE]
   └─ Item ID = 'id2' [UNIT NEGATIVE]
```

#### Case 2: Already Has Item-ID Children ✅
**Scenario:** Subdivision already has Item-ID based children
```
└─ Custom Attr 1 OTHERS [SUBDIVISION]
   ├─ Item ID OTHERS [UNIT POSITIVE]
   └─ Item ID = 'existing_id' [UNIT NEGATIVE]
```

**Action:** Add more Item-ID exclusions as siblings (same dimension type):
```
└─ Custom Attr 1 OTHERS [SUBDIVISION]
   ├─ Item ID OTHERS [UNIT POSITIVE, €0.20]
   ├─ Item ID = 'existing_id' [UNIT NEGATIVE]
   ├─ Item ID = 'id1' [UNIT NEGATIVE]  <- NEW
   └─ Item ID = 'id2' [UNIT NEGATIVE]  <- NEW
```

#### Case 3: Has Non-Item-ID UNIT Children ✅
**Scenario:** Subdivision has UNIT children of a different dimension (e.g., Custom Attr)
```
└─ Custom Attr 1 OTHERS [SUBDIVISION]
   ├─ Custom Attr 2 = 'value1' [UNIT POSITIVE]
   ├─ Custom Attr 2 = 'value2' [UNIT POSITIVE]
   └─ Custom Attr 2 OTHERS [UNIT POSITIVE]
```

**Problem:** Cannot add Item-ID units as siblings (different dimension type)

**Action:** Convert UNITs to SUBDIVISIONs and add Item-ID level below each:
```
└─ Custom Attr 1 OTHERS [SUBDIVISION]
   ├─ Custom Attr 2 = 'value1' [SUBDIVISION]  <- Converted from UNIT
   │  ├─ Item ID OTHERS [UNIT POSITIVE, €0.20]
   │  ├─ Item ID = 'id1' [UNIT NEGATIVE]
   │  └─ Item ID = 'id2' [UNIT NEGATIVE]
   ├─ Custom Attr 2 = 'value2' [SUBDIVISION]  <- Converted from UNIT
   │  ├─ Item ID OTHERS [UNIT POSITIVE, €0.20]
   │  ├─ Item ID = 'id1' [UNIT NEGATIVE]
   │  └─ Item ID = 'id2' [UNIT NEGATIVE]
   └─ Custom Attr 2 OTHERS [SUBDIVISION]  <- Converted from UNIT
      ├─ Item ID OTHERS [UNIT POSITIVE, €0.20]
      ├─ Item ID = 'id1' [UNIT NEGATIVE]
      └─ Item ID = 'id2' [UNIT NEGATIVE]
```

#### Case 4: Has Non-Item-ID SUBDIVISION Children ⚠️
**Scenario:** Subdivision has SUBDIVISION children of another dimension
```
└─ Custom Attr 1 OTHERS [SUBDIVISION]
   ├─ Custom Attr 2 = 'value1' [SUBDIVISION]
   │  └─ (deeper structure)
   └─ Custom Attr 2 OTHERS [SUBDIVISION]
      └─ (deeper structure)
```

**Action:** Skip (this is not actually the lowest level - the children are deeper)

## Multiple Subdivisions at Same Level ✅
If there are multiple subdivisions at the same lowest level, ALL of them get Item-ID exclusions:

```
Root [SUBDIVISION]
└─ Custom Attr 0 = 'a' [SUBDIVISION]
   ├─ Custom Attr 1 OTHERS [SUBDIVISION]      <- Depth 2, gets exclusions
   │  ├─ Item ID OTHERS [UNIT]
   │  └─ Item IDs excluded...
   ├─ Custom Attr 1 = 'something' [SUBDIVISION]  <- Depth 2, gets exclusions
   │  ├─ Item ID OTHERS [UNIT]
   │  └─ Item IDs excluded...
   └─ Custom Attr 1 = 'promo' [UNIT NEGATIVE]
```

## Key Features
1. ✅ **Preserves existing tree structure** - Reads and works with current structure
2. ✅ **Handles all edge cases** - 4 different scenarios covered
3. ✅ **Respects API constraints** - All siblings use same dimension type
4. ✅ **Processes multiple branches** - All subdivisions at lowest level get exclusions
5. ✅ **Fallback to standard tree** - Creates new structure if no tree exists

## Usage
```python
from listing_tree import rebuild_tree_with_label_and_item_ids

rebuild_tree_with_label_and_item_ids(
    client=client,
    customer_id="123456789",
    ad_group_id=987654321,
    ad_group_name="a",  # Label to filter by (a, b, c, no data, no ean)
    item_ids=["item123", "item456", "item789"],  # IDs to exclude
    default_bid_micros=200_000  # €0.20
)
```
