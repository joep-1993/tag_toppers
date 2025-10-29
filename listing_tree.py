def rebuild_tree_with_label_and_item_ids(
    client,
    customer_id: str,
    ad_group_id: int,
    ad_group_name: str,
    item_ids=None,
    default_bid_micros: int = 200_000
):
    """
    Copies the entire existing listing tree structure and adds Item-ID exclusions
    at the lowest subdivision level(s). If multiple nodes exist at the same lowest
    level, Item-ID exclusions are added to all of them.

    Structure approach:
    - Reads existing tree from the ad group
    - Identifies all subdivision nodes at the deepest level
    - For each of those subdivisions, adds:
      ├─ Item ID OTHERS [POSITIVE, biddable] → Show all items
      └─ Specific Item IDs [NEGATIVE] → Block unwanted items

    Args:
        client: GoogleAdsClient instance
        customer_id: Customer ID
        ad_group_id: Ad group ID
        ad_group_name: Ad group name to extract label from
        item_ids: List of item IDs to EXCLUDE (negative targeting)
        default_bid_micros: Default bid in micros (default: 200,000 = €0.20)
    """
    import time

    if item_ids is None:
        item_ids = []

    # Extract label from ad group name
    keep_label_value = ad_group_name.lower().strip()
    valid_labels = ["a", "b", "c", "no data", "no ean"]

    if keep_label_value not in valid_labels:
        print(f"⚠️ Ad group name '{ad_group_name}' (lowercase: '{keep_label_value}') is not a valid label. Valid options: {valid_labels}. Skipping tree rebuild.")
        return

    # Step 1: Read existing tree structure
    ga_service = client.get_service("GoogleAdsService")
    ag_service = client.get_service("AdGroupService")
    ag_path = ag_service.ad_group_path(customer_id, ad_group_id)

    query = f"""
        SELECT
            ad_group_criterion.resource_name,
            ad_group_criterion.listing_group.type,
            ad_group_criterion.listing_group.parent_ad_group_criterion,
            ad_group_criterion.listing_group.case_value.product_custom_attribute.index,
            ad_group_criterion.listing_group.case_value.product_custom_attribute.value,
            ad_group_criterion.listing_group.case_value.product_item_id.value,
            ad_group_criterion.negative,
            ad_group_criterion.cpc_bid_micros
        FROM ad_group_criterion
        WHERE ad_group_criterion.ad_group = '{ag_path}'
            AND ad_group_criterion.type = 'LISTING_GROUP'
    """

    try:
        results = list(ga_service.search(customer_id=customer_id, query=query))
    except Exception as e:
        print(f"❌ Error reading existing tree: {e}")
        return

    if not results:
        print("ℹ️ No existing tree found. Creating new tree structure.")
        # Fall back to creating standard tree (with default promo exclusion)
        _create_standard_tree(client, customer_id, ad_group_id, keep_label_value, item_ids, default_bid_micros, custom_label_structures=[{'index': 'INDEX1', 'value': 'promo', 'negative': True, 'bid_micros': None}])
        return

    # Step 2: Build tree structure map and find lowest subdivision level
    tree_map = {}
    depth_map = {}

    for row in results:
        criterion = row.ad_group_criterion
        res_name = criterion.resource_name
        lg = criterion.listing_group
        parent = lg.parent_ad_group_criterion

        tree_map[res_name] = {
            'resource_name': res_name,
            'type': lg.type_.name,
            'parent': parent if parent else None,
            'case_value': lg.case_value,
            'negative': criterion.negative,
            'bid_micros': criterion.cpc_bid_micros,
            'children': []
        }

    # Build parent-child relationships
    for res_name, node_data in tree_map.items():
        parent = node_data['parent']
        if parent and parent in tree_map:
            tree_map[parent]['children'].append(res_name)

    # Calculate depths
    def calculate_depth(res_name):
        if res_name in depth_map:
            return depth_map[res_name]
        parent = tree_map[res_name]['parent']
        if not parent:
            depth = 0
        else:
            depth = 1 + calculate_depth(parent)
        depth_map[res_name] = depth
        return depth

    for res_name in tree_map.keys():
        calculate_depth(res_name)

    # Find all subdivisions at the deepest level
    subdivision_nodes = [res_name for res_name, node in tree_map.items()
                        if node['type'] == 'SUBDIVISION']

    if not subdivision_nodes:
        print("⚠️ No subdivision nodes found in existing tree. Cannot add Item-ID exclusions.")
        return

    max_depth = max(depth_map[res_name] for res_name in subdivision_nodes)
    lowest_subdivisions = [res_name for res_name in subdivision_nodes
                          if depth_map[res_name] == max_depth]

    print(f"Found {len(lowest_subdivisions)} subdivision(s) at lowest level (depth {max_depth})")

    # Collect ALL custom label structures from the original tree (both exclusions and subdivisions)
    custom_label_structures = []
    for res_name, node in tree_map.items():
        case_val = node['case_value']
        if (case_val and
            case_val._pb.WhichOneof("dimension") == "product_custom_attribute"):
            index_name = case_val.product_custom_attribute.index.name
            value = case_val.product_custom_attribute.value

            # Skip the label itself (INDEX0 with the keep_label_value) and OTHERS cases
            if index_name == 'INDEX0':
                continue
            if not value or value == '':  # OTHERS case
                continue

            # Store all custom label units (both negative and positive)
            if node['type'] == 'UNIT':
                custom_label_structures.append({
                    'index': index_name,
                    'value': value,
                    'negative': node['negative'],
                    'bid_micros': node['bid_micros']
                })

    if custom_label_structures:
        print(f"    ℹ️ Original tree has {len(custom_label_structures)} custom label structure(s), will preserve them:")
        for struct in custom_label_structures:
            neg_str = "[NEGATIVE]" if struct['negative'] else "[POSITIVE]"
            print(f"       - {struct['index']}: '{struct['value']}' {neg_str}")

    # Step 3: For each lowest subdivision, add Item-ID exclusions
    agc_service = client.get_service("AdGroupCriterionService")

    # Deduplicate item IDs
    unique_item_ids = list(dict.fromkeys(item_ids)) if item_ids else []

    # Print Item-IDs being excluded
    if unique_item_ids:
        print(f"📋 Excluding {len(unique_item_ids)} Item-ID(s) from label '{keep_label_value}':")
        for idx, item_id in enumerate(unique_item_ids[:10], 1):  # Show first 10
            print(f"   {idx}. '{item_id}'")
        if len(unique_item_ids) > 10:
            print(f"   ... and {len(unique_item_ids) - 10} more")

    subdivisions_processed = 0

    for sub_res_name in lowest_subdivisions:
        print(f"  Processing subdivision: {sub_res_name}")

        children = tree_map[sub_res_name]['children']

        if not children:
            # Case 1: No children - directly add Item-ID structure
            print(f"    No children found, adding Item-ID structure directly")
            _add_item_id_exclusions_to_subdivision(
                client, customer_id, ad_group_id, agc_service,
                sub_res_name, unique_item_ids, default_bid_micros
            )
            subdivisions_processed += 1
            continue

        # Check what type of children exist
        has_item_id_children = False
        has_positive_non_item_id_unit_children = False
        has_non_item_id_subdivision_children = False

        for child_res in children:
            child_node = tree_map[child_res]
            case_val = child_node['case_value']

            if case_val and case_val._pb.WhichOneof("dimension") == "product_item_id":
                has_item_id_children = True
            elif child_node['type'] == 'UNIT' and not child_node['negative']:
                # Only count POSITIVE (non-negative) units as needing special handling
                # NEGATIVE units are exclusions and should be left as siblings
                has_positive_non_item_id_unit_children = True
            elif child_node['type'] == 'SUBDIVISION':
                has_non_item_id_subdivision_children = True

        if has_item_id_children:
            # Case 2: Already has Item-ID children - need to rebuild entire tree
            print(f"    Already has Item-ID children, rebuilding entire tree to ensure consistency")
            print(f"    🔄 Removing existing tree and rebuilding with {len(unique_item_ids)} Item-ID exclusion(s)")

            # Remove the entire existing tree
            try:
                from GSD_tagtoppers import safe_remove_entire_listing_tree
                safe_remove_entire_listing_tree(client, customer_id, str(ad_group_id))
            except Exception as e:
                print(f"    ⚠️ Warning during tree removal: {e}")

            # Wait longer for deletion to be fully processed by Google Ads API
            print(f"    ⏳ Waiting 5 seconds for deletion to complete...")
            time.sleep(5)

            # Rebuild from scratch with all Item-ID exclusions, preserving all custom label structures
            _create_standard_tree(client, customer_id, ad_group_id, keep_label_value, unique_item_ids, default_bid_micros, custom_label_structures=custom_label_structures)

            print(f"    ✅ Tree rebuilt successfully")
            # Mark as processed and exit - we've handled the entire ad group
            subdivisions_processed += 1
            break  # No need to process other subdivisions, we rebuilt the entire tree

        elif has_positive_non_item_id_unit_children:
            # Case 3: Has POSITIVE non-Item-ID UNIT children - need to rebuild tree from scratch
            print(f"    Has POSITIVE non-Item-ID UNIT children, rebuilding entire tree to preserve structures")
            print(f"    🔄 Removing existing tree and rebuilding with {len(unique_item_ids)} Item-ID exclusion(s)")

            # Remove the entire existing tree
            try:
                from GSD_tagtoppers import safe_remove_entire_listing_tree
                safe_remove_entire_listing_tree(client, customer_id, str(ad_group_id))
            except Exception as e:
                print(f"    ⚠️ Warning during tree removal: {e}")

            # Wait longer for deletion to be fully processed by Google Ads API
            print(f"    ⏳ Waiting 5 seconds for deletion to complete...")
            time.sleep(5)

            # Rebuild from scratch with all Item-ID exclusions, preserving all custom label structures
            _create_standard_tree(client, customer_id, ad_group_id, keep_label_value, unique_item_ids, default_bid_micros, custom_label_structures=custom_label_structures)

            print(f"    ✅ Tree rebuilt successfully")
            # Mark as processed and exit - we've handled the entire ad group
            subdivisions_processed += 1
            break  # No need to process other subdivisions, we rebuilt the entire tree

        elif has_non_item_id_subdivision_children:
            # Case 4: Has non-Item-ID SUBDIVISION children - these are deeper, recurse or skip
            print(f"    Has non-Item-ID SUBDIVISION children - these are deeper levels")
            print(f"    ⚠️ This subdivision is not actually the lowest level, skipping")

    unique_count = len(unique_item_ids)
    total_count = len(item_ids)
    if total_count > unique_count:
        print(f"✅ Tree updated: Added exclusions for {unique_count} unique Item IDs ({total_count-unique_count} duplicates removed) to {subdivisions_processed} subdivision(s)")
    else:
        print(f"✅ Tree updated: Added exclusions for {unique_count} Item IDs to {subdivisions_processed} subdivision(s)")


def _add_item_id_exclusions_to_subdivision(
    client, customer_id, ad_group_id, agc_service,
    parent_res_name, unique_item_ids, default_bid_micros
):
    """
    Adds Item-ID OTHERS (positive) and specific Item-ID exclusions (negative)
    to a subdivision node.
    """
    operations = []

    # Add Item ID OTHERS (positive, biddable)
    dim_itemid_others = client.get_type("ListingDimensionInfo")
    client.copy_from(
        dim_itemid_others.product_item_id,
        client.get_type("ProductItemIdInfo"),
    )

    operations.append(
        _create_listing_group_unit_biddable(
            client=client,
            customer_id=customer_id,
            ad_group_id=str(ad_group_id),
            parent_ad_group_criterion_resource_name=parent_res_name,
            listing_dimension_info=dim_itemid_others,
            targeting_negative=False,
            cpc_bid_micros=default_bid_micros
        )
    )

    # Add specific Item IDs as NEGATIVE units
    if unique_item_ids:
        for item_id in unique_item_ids:
            dim_item = client.get_type("ListingDimensionInfo")
            dim_item.product_item_id.value = str(item_id)
            operations.append(
                _create_listing_group_unit_biddable(
                    client=client,
                    customer_id=customer_id,
                    ad_group_id=str(ad_group_id),
                    parent_ad_group_criterion_resource_name=parent_res_name,
                    listing_dimension_info=dim_item,
                    targeting_negative=True,
                    cpc_bid_micros=None
                )
            )

    # Execute operations
    try:
        agc_service.mutate_ad_group_criteria(customer_id=customer_id, operations=operations)
        print(f"    ✅ Added Item-ID OTHERS + {len(unique_item_ids)} exclusion(s)")
    except Exception as e:
        print(f"    ❌ Error adding Item-ID exclusions: {e}")
        raise


def _convert_units_to_subdivisions_and_add_item_ids(
    client, customer_id, ad_group_id, agc_service,
    parent_res_name, children_res_names, tree_map, unique_item_ids, default_bid_micros
):
    """
    Converts existing UNIT children to SUBDIVISION children and adds Item-ID
    exclusions under each new subdivision.

    This is needed when the lowest subdivision has non-Item-ID UNIT children,
    because we can't add Item-ID units as siblings (all siblings must be same type).
    """
    import time

    print(f"    Converting {len(children_res_names)} UNIT(s) to SUBDIVISION(s)")

    # Step 1: Remove all existing UNIT children
    remove_ops = []
    children_data = []

    for child_res in children_res_names:
        child_node = tree_map[child_res]
        if child_node['type'] == 'UNIT':
            children_data.append({
                'resource_name': child_res,
                'case_value': child_node['case_value'],
                'negative': child_node['negative'],
                'bid_micros': child_node['bid_micros']
            })
            remove_op = client.get_type("AdGroupCriterionOperation")
            remove_op.remove = child_res
            remove_ops.append(remove_op)

    if remove_ops:
        try:
            agc_service.mutate_ad_group_criteria(customer_id=customer_id, operations=remove_ops)
            print(f"    Removed {len(remove_ops)} existing UNIT(s)")
            time.sleep(0.5)
        except Exception as e:
            print(f"    ❌ Error removing UNITs: {e}")
            raise

    # Step 2: Recreate as SUBDIVISIONs and add Item-ID children to each
    for child_data in children_data:
        # Create subdivision with same case_value
        create_ops = []

        # Create the subdivision
        sub_op = client.get_type("AdGroupCriterionOperation")
        sub_criterion = sub_op.create

        global_last_criterion_id = getattr(_create_listing_group_unit_biddable, 'last_id', 0)
        global_last_criterion_id -= 1
        _create_listing_group_unit_biddable.last_id = global_last_criterion_id

        sub_criterion.resource_name = client.get_service(
            "AdGroupCriterionService"
        ).ad_group_criterion_path(customer_id, str(ad_group_id), str(global_last_criterion_id))
        sub_criterion.status = client.enums.AdGroupCriterionStatusEnum.ENABLED

        sub_criterion.listing_group.type_ = client.enums.ListingGroupTypeEnum.SUBDIVISION
        sub_criterion.listing_group.parent_ad_group_criterion = parent_res_name
        if child_data['case_value']:
            client.copy_from(sub_criterion.listing_group.case_value, child_data['case_value'])

        new_sub_res_tmp = sub_criterion.resource_name
        create_ops.append(sub_op)

        # Execute subdivision creation
        try:
            resp = agc_service.mutate_ad_group_criteria(customer_id=customer_id, operations=create_ops)
            new_sub_res_actual = resp.results[0].resource_name
            print(f"    Created subdivision: {new_sub_res_actual}")
            time.sleep(0.3)
        except Exception as e:
            print(f"    ❌ Error creating subdivision: {e}")
            continue

        # Add Item-ID exclusions to this new subdivision
        _add_item_id_exclusions_to_subdivision(
            client, customer_id, ad_group_id, agc_service,
            new_sub_res_actual, unique_item_ids, default_bid_micros
        )
        time.sleep(0.3)


def _create_listing_group_unit_biddable(
        client,
        customer_id,
        ad_group_id,
        parent_ad_group_criterion_resource_name,
        listing_dimension_info,
        targeting_negative,
        cpc_bid_micros=None
):
    """Helper function to create listing group unit (biddable or negative)"""
    global_last_criterion_id = getattr(_create_listing_group_unit_biddable, 'last_id', 0)
    global_last_criterion_id -= 1
    _create_listing_group_unit_biddable.last_id = global_last_criterion_id

    operation = client.get_type("AdGroupCriterionOperation")
    criterion = operation.create
    criterion.resource_name = client.get_service(
        "AdGroupCriterionService"
    ).ad_group_criterion_path(customer_id, ad_group_id, str(global_last_criterion_id))
    criterion.status = client.enums.AdGroupCriterionStatusEnum.ENABLED
    if cpc_bid_micros and targeting_negative == False:
        criterion.cpc_bid_micros = cpc_bid_micros

    listing_group = criterion.listing_group
    listing_group.type_ = client.enums.ListingGroupTypeEnum.UNIT
    listing_group.parent_ad_group_criterion = parent_ad_group_criterion_resource_name

    if listing_dimension_info is not None:
        client.copy_from(listing_group.case_value, listing_dimension_info)

    if targeting_negative:
        criterion.negative = True
    return operation


def _create_standard_tree(client, customer_id, ad_group_id, keep_label_value, item_ids, default_bid_micros, custom_label_structures=None):
    """
    Creates standard tree structure when no existing tree is found or needs to be rebuilt:
    Root SUBDIVISION
    ├─ Custom Attr 0 OTHERS [NEGATIVE] → Blocks everything without the label
    └─ Custom Attr 0 = <label> [SUBDIVISION]
       ├─ Custom Attr X OTHERS [SUBDIVISION] → Subdivision for the highest custom label index
       │  ├─ Item ID OTHERS [POSITIVE, biddable] → Show all items with this custom label
       │  └─ Specific Item IDs [NEGATIVE] → Block unwanted items
       └─ Custom Attr X = <value> [SUBDIVISION/UNIT] → Preserved custom label structures (both positive and negative)
          ├─ Item ID OTHERS [POSITIVE, biddable] (if positive)
          └─ Specific Item IDs [NEGATIVE] (if positive)

    Args:
        custom_label_structures: List of dicts with 'index', 'value', 'negative', and 'bid_micros' for custom label structures to preserve
    """
    import time

    # Remove existing tree directly
    print(f"    Checking for existing tree to remove...")
    ag_service = client.get_service("AdGroupService")
    agc_service = client.get_service("AdGroupCriterionService")
    ga_service = client.get_service("GoogleAdsService")
    ag_path = ag_service.ad_group_path(customer_id, str(ad_group_id))

    query = f"""
        SELECT ad_group_criterion.resource_name,
               ad_group_criterion.listing_group.parent_ad_group_criterion
        FROM ad_group_criterion
        WHERE ad_group_criterion.ad_group = '{ag_path}'
          AND ad_group_criterion.type = 'LISTING_GROUP'
    """

    try:
        existing_criteria = list(ga_service.search(customer_id=customer_id, query=query))
        if existing_criteria:
            # Find root (no parent)
            root = None
            for row in existing_criteria:
                if not row.ad_group_criterion.listing_group.parent_ad_group_criterion:
                    root = row
                    break

            if root:
                print(f"    Removing existing tree (root: {root.ad_group_criterion.resource_name})...")
                op = client.get_type("AdGroupCriterionOperation")
                op.remove = root.ad_group_criterion.resource_name
                agc_service.mutate_ad_group_criteria(customer_id=customer_id, operations=[op])
                print(f"    Tree removed successfully")
                # Wait for deletion to propagate
                print(f"    ⏳ Waiting 5 seconds for deletion to propagate...")
                time.sleep(5)
            else:
                print(f"    No root found in existing tree")
        else:
            print(f"    No existing tree found")
    except Exception as e:
        print(f"    ⚠️ Error during tree removal check: {e}")
        # Wait even if removal failed (tree might already be gone)
        print(f"    ⏳ Waiting 3 seconds before proceeding...")
        time.sleep(3)

    # Initialize custom_label_structures if None
    if custom_label_structures is None:
        custom_label_structures = []

    # Map index names to enum values
    index_map = {
        'INDEX0': client.enums.ProductCustomAttributeIndexEnum.INDEX0,
        'INDEX1': client.enums.ProductCustomAttributeIndexEnum.INDEX1,
        'INDEX2': client.enums.ProductCustomAttributeIndexEnum.INDEX2,
        'INDEX3': client.enums.ProductCustomAttributeIndexEnum.INDEX3,
        'INDEX4': client.enums.ProductCustomAttributeIndexEnum.INDEX4,
    }

    # Separate positive and negative custom label structures
    positive_structures = [s for s in custom_label_structures if not s['negative']]
    negative_structures = [s for s in custom_label_structures if s['negative']]

    # Find the highest custom label index (for creating OTHERS subdivisions)
    highest_index_num = 1  # Default to INDEX1 for backward compatibility
    for struct in custom_label_structures:
        index_name = struct['index']
        if index_name in index_map:
            index_num = int(index_name[-1])  # Extract number from 'INDEXN'
            if index_num > highest_index_num:
                highest_index_num = index_num

    agc = client.get_service("AdGroupCriterionService")
    product_custom_enum = client.enums.ProductCustomAttributeIndexEnum

    global_last_criterion_id = -1

    def next_id():
        nonlocal global_last_criterion_id
        global_last_criterion_id -= 1
        return str(global_last_criterion_id)

    def create_listing_group_subdivision(parent_ad_group_criterion_resource_name=None, listing_dimension_info=None):
        operation = client.get_type("AdGroupCriterionOperation")
        ad_group_criterion = operation.create
        ad_group_criterion.resource_name = client.get_service(
            "AdGroupCriterionService"
        ).ad_group_criterion_path(customer_id, str(ad_group_id), next_id())
        ad_group_criterion.status = client.enums.AdGroupCriterionStatusEnum.ENABLED

        listing_group_info = ad_group_criterion.listing_group
        listing_group_info.type_ = client.enums.ListingGroupTypeEnum.SUBDIVISION
        if parent_ad_group_criterion_resource_name is not None:
            listing_group_info.parent_ad_group_criterion = parent_ad_group_criterion_resource_name
        if listing_dimension_info is not None:
            client.copy_from(listing_group_info.case_value, listing_dimension_info)
        return operation

    def create_unit(parent_resource, dimension_info, negative, bid_micros=None):
        operation = client.get_type("AdGroupCriterionOperation")
        criterion = operation.create
        criterion.resource_name = client.get_service(
            "AdGroupCriterionService"
        ).ad_group_criterion_path(customer_id, str(ad_group_id), next_id())
        criterion.status = client.enums.AdGroupCriterionStatusEnum.ENABLED
        if bid_micros and not negative:
            criterion.cpc_bid_micros = bid_micros

        listing_group = criterion.listing_group
        listing_group.type_ = client.enums.ListingGroupTypeEnum.UNIT
        listing_group.parent_ad_group_criterion = parent_resource

        if dimension_info is not None:
            client.copy_from(listing_group.case_value, dimension_info)

        if negative:
            criterion.negative = True
        return operation

    # MUTATE 1: Root + Custom Attr 0 OTHERS (negative)
    ops1 = []

    root_op = create_listing_group_subdivision(None, None)
    root_tmp = root_op.create.resource_name
    ops1.append(root_op)

    dim_attr0_others = client.get_type("ListingDimensionInfo")
    client.copy_from(
        dim_attr0_others.product_custom_attribute,
        client.get_type("ProductCustomAttributeInfo"),
    )
    dim_attr0_others.product_custom_attribute.index = product_custom_enum.INDEX0
    ops1.append(create_unit(root_tmp, dim_attr0_others, True, None))

    resp1 = agc.mutate_ad_group_criteria(customer_id=customer_id, operations=ops1)
    root_actual = resp1.results[0].resource_name
    time.sleep(0.5)

    # MUTATE 2: Label subdivision + chain of Custom Attr OTHERS subdivisions + Item ID OTHERS unit
    ops2 = []

    # Create label subdivision under root
    dim_label = client.get_type("ListingDimensionInfo")
    dim_label.product_custom_attribute.index = product_custom_enum.INDEX0
    dim_label.product_custom_attribute.value = keep_label_value
    label_sub_op = create_listing_group_subdivision(root_actual, dim_label)
    label_sub_tmp = label_sub_op.create.resource_name
    ops2.append(label_sub_op)

    # Create OTHERS subdivision for the highest custom label index only
    # All custom label exclusions will be siblings to this OTHERS subdivision
    index_enum = index_map[f'INDEX{highest_index_num}']

    dim_attr_others = client.get_type("ListingDimensionInfo")
    client.copy_from(
        dim_attr_others.product_custom_attribute,
        client.get_type("ProductCustomAttributeInfo"),
    )
    dim_attr_others.product_custom_attribute.index = index_enum

    attr_sub_op = create_listing_group_subdivision(label_sub_tmp, dim_attr_others)
    attr_sub_tmp = attr_sub_op.create.resource_name
    ops2.append(attr_sub_op)

    # Track parent for adding exclusions - they should be siblings to OTHERS subdivision
    # So their parent is the label subdivision
    highest_others_tmp = attr_sub_tmp
    exclusions_parent_tmp = label_sub_tmp

    # Add Item ID OTHERS unit under the OTHERS subdivision
    dim_itemid_others = client.get_type("ListingDimensionInfo")
    client.copy_from(
        dim_itemid_others.product_item_id,
        client.get_type("ProductItemIdInfo"),
    )
    ops2.append(create_unit(highest_others_tmp, dim_itemid_others, False, default_bid_micros))

    resp2 = agc.mutate_ad_group_criteria(customer_id=customer_id, operations=ops2)
    label_sub_actual = resp2.results[0].resource_name
    highest_others_actual = resp2.results[1].resource_name
    exclusions_parent_actual = label_sub_actual
    time.sleep(0.5)

    # MUTATE 3A: Add Item ID exclusions under the OTHERS subdivision
    ops3a = []
    unique_item_ids = list(dict.fromkeys(item_ids)) if item_ids else []

    if unique_item_ids:
        for item_id in unique_item_ids:
            dim_item = client.get_type("ListingDimensionInfo")
            dim_item.product_item_id.value = str(item_id)
            ops3a.append(create_unit(highest_others_actual, dim_item, True, None))

    if ops3a:
        agc.mutate_ad_group_criteria(customer_id=customer_id, operations=ops3a)
        time.sleep(0.5)

    # MUTATE 3B: Add custom label structures
    # For positive structures: create as subdivisions with Item ID children sequentially
    # For negative structures: create as exclusion units

    # Create each positive structure as a subdivision with its Item ID children immediately
    for struct in positive_structures:
        index_name = struct['index']
        value = struct['value']

        if index_name not in index_map:
            print(f"⚠️ Unknown custom label index '{index_name}', skipping structure for value '{value}'")
            continue

        index_enum = index_map[index_name]

        # Create custom label subdivision under the label subdivision (sibling to OTHERS)
        dim_struct = client.get_type("ListingDimensionInfo")
        dim_struct.product_custom_attribute.index = index_enum
        dim_struct.product_custom_attribute.value = value
        struct_sub_op = create_listing_group_subdivision(exclusions_parent_actual, dim_struct)

        # Create subdivision
        resp3b_sub = agc.mutate_ad_group_criteria(customer_id=customer_id, operations=[struct_sub_op])
        struct_actual = resp3b_sub.results[0].resource_name
        time.sleep(0.3)

        # Immediately add Item ID OTHERS and Item ID exclusions as children
        ops3b_children = []

        # Add Item ID OTHERS (positive, with original bid)
        dim_itemid_others = client.get_type("ListingDimensionInfo")
        client.copy_from(
            dim_itemid_others.product_item_id,
            client.get_type("ProductItemIdInfo"),
        )
        ops3b_children.append(create_unit(struct_actual, dim_itemid_others, False, struct.get('bid_micros', default_bid_micros)))

        # Add Item ID exclusions
        if unique_item_ids:
            for item_id in unique_item_ids:
                dim_item = client.get_type("ListingDimensionInfo")
                dim_item.product_item_id.value = str(item_id)
                ops3b_children.append(create_unit(struct_actual, dim_item, True, None))

        if ops3b_children:
            agc.mutate_ad_group_criteria(customer_id=customer_id, operations=ops3b_children)
            time.sleep(0.3)

    # Finally, add negative structures as exclusion units (siblings to OTHERS)
    ops3c_negatives = []
    for struct in negative_structures:
        index_name = struct['index']
        value = struct['value']

        if index_name not in index_map:
            print(f"⚠️ Unknown custom label index '{index_name}', skipping exclusion for value '{value}'")
            continue

        index_enum = index_map[index_name]

        # Create negative unit under the label subdivision (sibling to OTHERS)
        dim_excl = client.get_type("ListingDimensionInfo")
        dim_excl.product_custom_attribute.index = index_enum
        dim_excl.product_custom_attribute.value = value
        ops3c_negatives.append(create_unit(exclusions_parent_actual, dim_excl, True, None))

    if ops3c_negatives:
        agc.mutate_ad_group_criteria(customer_id=customer_id, operations=ops3c_negatives)

    # Print success message
    unique_count = len(unique_item_ids)
    total_count = len(item_ids) if item_ids else 0
    struct_msg = ""
    if positive_structures:
        struct_msg += f" + {len(positive_structures)} positive custom label structure(s)"
    if negative_structures:
        struct_msg += f" + {len(negative_structures)} negative custom label structure(s)"

    if total_count > unique_count:
        print(f"✅ Standard tree created: Allow label '{keep_label_value}', block {unique_count} unique Item IDs ({total_count-unique_count} duplicates removed){struct_msg}.")
    else:
        print(f"✅ Standard tree created: Allow label '{keep_label_value}', block {unique_count} Item IDs{struct_msg}.")
