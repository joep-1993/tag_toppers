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
        # Fall back to creating standard tree (with promo exclusion by default)
        _create_standard_tree(client, customer_id, ad_group_id, keep_label_value, item_ids, default_bid_micros, has_promo=True)
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

    # Check if original tree has "promo" exclusion
    has_promo_exclusion = False
    for res_name, node in tree_map.items():
        case_val = node['case_value']
        if (case_val and
            case_val._pb.WhichOneof("dimension") == "product_custom_attribute" and
            case_val.product_custom_attribute.index.name == "INDEX1" and
            case_val.product_custom_attribute.value == "promo" and
            node['negative']):
            has_promo_exclusion = True
            break

    if has_promo_exclusion:
        print(f"    ℹ️ Original tree has 'promo' exclusion, will preserve it")

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
        has_non_item_id_unit_children = False
        has_non_item_id_subdivision_children = False

        for child_res in children:
            child_node = tree_map[child_res]
            case_val = child_node['case_value']

            if case_val and case_val._pb.WhichOneof("dimension") == "product_item_id":
                has_item_id_children = True
            elif child_node['type'] == 'UNIT':
                has_non_item_id_unit_children = True
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
            except:
                pass

            # Wait for deletion to be fully processed by Google Ads API
            print(f"    ⏳ Waiting 3 seconds for deletion to complete...")
            time.sleep(3)

            # Rebuild from scratch with all Item-ID exclusions, preserving promo if it existed
            _create_standard_tree(client, customer_id, ad_group_id, keep_label_value, unique_item_ids, default_bid_micros, has_promo=has_promo_exclusion)

            print(f"    ✅ Tree rebuilt successfully")
            # Mark as processed and exit - we've handled the entire ad group
            subdivisions_processed += 1
            break  # No need to process other subdivisions, we rebuilt the entire tree

        elif has_non_item_id_unit_children:
            # Case 3: Has non-Item-ID UNIT children - need to rebuild tree from scratch
            print(f"    Has non-Item-ID UNIT children, rebuilding entire tree")
            print(f"    🔄 Removing existing tree and rebuilding with {len(unique_item_ids)} Item-ID exclusion(s)")

            # Remove the entire existing tree
            try:
                from GSD_tagtoppers import safe_remove_entire_listing_tree
                safe_remove_entire_listing_tree(client, customer_id, str(ad_group_id))
            except:
                pass

            # Wait for deletion to be fully processed by Google Ads API
            print(f"    ⏳ Waiting 3 seconds for deletion to complete...")
            time.sleep(3)

            # Rebuild from scratch with all Item-ID exclusions, preserving promo if it existed
            _create_standard_tree(client, customer_id, ad_group_id, keep_label_value, unique_item_ids, default_bid_micros, has_promo=has_promo_exclusion)

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


def _create_standard_tree(client, customer_id, ad_group_id, keep_label_value, item_ids, default_bid_micros, has_promo=True):
    """
    Creates standard tree structure when no existing tree is found:
    Root SUBDIVISION
    ├─ Custom Attr 0 OTHERS [NEGATIVE] → Blocks everything without the label
    ├─ Custom Attr 0 = <label> [SUBDIVISION]
    │  ├─ Custom Attr 1 OTHERS [SUBDIVISION]
    │  │  ├─ Item ID OTHERS [POSITIVE, biddable] → Show all items with the label
    │  │  └─ Specific Item IDs [NEGATIVE] → Block unwanted items
    │  └─ Custom Attr 1 = "promo" [NEGATIVE] → Block promo items (only if has_promo=True)
    """
    import time

    # Import safe_remove_entire_listing_tree if available
    try:
        from GSD_tagtoppers import safe_remove_entire_listing_tree
        safe_remove_entire_listing_tree(client, customer_id, str(ad_group_id))
    except:
        pass

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

    # MUTATE 2: Label subdivision + Custom Attr 1 OTHERS subdivision + Item ID OTHERS unit
    ops2 = []

    dim_label = client.get_type("ListingDimensionInfo")
    dim_label.product_custom_attribute.index = product_custom_enum.INDEX0
    dim_label.product_custom_attribute.value = keep_label_value
    label_sub_op = create_listing_group_subdivision(root_actual, dim_label)
    label_sub_tmp = label_sub_op.create.resource_name
    ops2.append(label_sub_op)

    dim_attr1_others = client.get_type("ListingDimensionInfo")
    client.copy_from(
        dim_attr1_others.product_custom_attribute,
        client.get_type("ProductCustomAttributeInfo"),
    )
    dim_attr1_others.product_custom_attribute.index = product_custom_enum.INDEX1
    attr1_sub_op = create_listing_group_subdivision(label_sub_tmp, dim_attr1_others)
    attr1_sub_tmp = attr1_sub_op.create.resource_name
    ops2.append(attr1_sub_op)

    dim_itemid_others = client.get_type("ListingDimensionInfo")
    client.copy_from(
        dim_itemid_others.product_item_id,
        client.get_type("ProductItemIdInfo"),
    )
    ops2.append(create_unit(attr1_sub_tmp, dim_itemid_others, False, default_bid_micros))

    resp2 = agc.mutate_ad_group_criteria(customer_id=customer_id, operations=ops2)
    label_sub_actual = resp2.results[0].resource_name
    attr1_sub_actual = resp2.results[1].resource_name
    time.sleep(0.5)

    # MUTATE 3: Item ID exclusions + promo exclusion
    ops3 = []

    unique_item_ids = list(dict.fromkeys(item_ids)) if item_ids else []

    if unique_item_ids:
        for item_id in unique_item_ids:
            dim_item = client.get_type("ListingDimensionInfo")
            dim_item.product_item_id.value = str(item_id)
            ops3.append(create_unit(attr1_sub_actual, dim_item, True, None))

    # Only add promo exclusion if it was in the original tree
    if has_promo:
        dim_promo = client.get_type("ListingDimensionInfo")
        dim_promo.product_custom_attribute.index = product_custom_enum.INDEX1
        dim_promo.product_custom_attribute.value = "promo"
        ops3.append(create_unit(label_sub_actual, dim_promo, True, None))

    if ops3:
        agc.mutate_ad_group_criteria(customer_id=customer_id, operations=ops3)
        unique_count = len(unique_item_ids)
        total_count = len(item_ids) if item_ids else 0

        promo_msg = " + 'promo' items" if has_promo else ""

        if total_count > unique_count:
            print(f"✅ Standard tree created: Allow label '{keep_label_value}', block {unique_count} unique Item IDs ({total_count-unique_count} duplicates removed){promo_msg}.")
        else:
            print(f"✅ Standard tree created: Allow label '{keep_label_value}', block {unique_count} Item IDs{promo_msg}.")
    else:
        if has_promo:
            print(f"✅ Standard tree created: Allow label '{keep_label_value}', block 'promo' items.")
        else:
            print(f"✅ Standard tree created: Allow label '{keep_label_value}'.")
