#!/usr/bin/env python3
"""
Test script to verify that custom label exclusions are preserved
when adding item ID exclusions.

Test on:
- Customer ID: 7938980174
- Campaign ID: 18722468828
- Ad Group ID: 144284844193
"""

import os
from google.ads.googleads.client import GoogleAdsClient
from listing_tree import rebuild_tree_with_label_and_item_ids

# Set up Google Ads client
def load_credentials():
    """Load credentials from environment or creds file"""
    creds = {
        'client_id': os.getenv("GOOGLE_CLIENT_ID"),
        'client_secret': os.getenv("GOOGLE_CLIENT_SECRET"),
        'refresh_token': os.getenv("GOOGLE_REFRESH_TOKEN"),
        'developer_token': os.getenv("GOOGLE_DEVELOPER_TOKEN"),
        'login_customer_id': os.getenv("GOOGLE_LOGIN_CUSTOMER_ID")
    }

    # Load from creds file if any are missing
    if not all(creds.values()):
        creds_file = os.path.join(os.path.dirname(__file__), 'creds')
        if os.path.exists(creds_file):
            with open(creds_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('#') or not line:
                        continue
                    if '=' in line:
                        key, val = line.split('=', 1)
                        key = key.strip()
                        val = val.strip()
                        if key == 'GOOGLE_CLIENT_ID':
                            creds['client_id'] = val
                        elif key == 'GOOGLE_CLIENT_SECRET':
                            creds['client_secret'] = val
                        elif key == 'GOOGLE_REFRESH_TOKEN':
                            creds['refresh_token'] = val
                        elif key == 'GOOGLE_DEVELOPER_TOKEN':
                            creds['developer_token'] = val
                        elif key == 'GOOGLE_LOGIN_CUSTOMER_ID':
                            creds['login_customer_id'] = val

    return creds

creds = load_credentials()
client_id = creds['client_id']
client_secret = creds['client_secret']
refresh_token = creds['refresh_token']
developer_token = creds['developer_token']
login_customer_id = creds['login_customer_id']

google_ads_config = {
    "developer_token": developer_token,
    "refresh_token":  refresh_token,
    "client_id":      client_id,
    "client_secret":  client_secret,
    "login_customer_id": login_customer_id,
    "use_proto_plus": True,
}
client = GoogleAdsClient.load_from_dict(google_ads_config)

# Test parameters
customer_id = '7938980174'
campaign_id = '18722468828'
ad_group_id = 144284844193

# First, let's read the current tree to see what exclusions exist
print(f"=== Reading current tree structure for ad group {ad_group_id} ===\n")

ga_service = client.get_service("GoogleAdsService")
ag_service = client.get_service("AdGroupService")
ag_path = ag_service.ad_group_path(customer_id, ad_group_id)

# Get ad group name
ag_query = f"""
    SELECT ad_group.id, ad_group.name
    FROM ad_group
    WHERE ad_group.id = {ad_group_id}
"""
ag_result = ga_service.search(customer_id=customer_id, query=ag_query)
ad_group_name = None
for row in ag_result:
    ad_group_name = row.ad_group.name
    print(f"Ad Group Name: {ad_group_name}")

query = f"""
    SELECT
        ad_group_criterion.resource_name,
        ad_group_criterion.listing_group.type,
        ad_group_criterion.listing_group.parent_ad_group_criterion,
        ad_group_criterion.listing_group.case_value.product_custom_attribute.index,
        ad_group_criterion.listing_group.case_value.product_custom_attribute.value,
        ad_group_criterion.listing_group.case_value.product_item_id.value,
        ad_group_criterion.negative
    FROM ad_group_criterion
    WHERE ad_group_criterion.ad_group = '{ag_path}'
        AND ad_group_criterion.type = 'LISTING_GROUP'
"""

try:
    results = list(ga_service.search(customer_id=customer_id, query=query))
    print(f"\nFound {len(results)} listing group criteria:\n")

    for row in results:
        criterion = row.ad_group_criterion
        lg = criterion.listing_group
        case_val = lg.case_value

        negative_str = "[NEGATIVE]" if criterion.negative else "[POSITIVE]"
        type_str = lg.type_.name

        # Check what dimension this is
        dimension = "ROOT"
        if case_val:
            dim_type = case_val._pb.WhichOneof("dimension")
            if dim_type == "product_custom_attribute":
                index = case_val.product_custom_attribute.index.name
                value = case_val.product_custom_attribute.value or "OTHERS"
                dimension = f"Custom Attr {index[-1]}: {value}"
            elif dim_type == "product_item_id":
                value = case_val.product_item_id.value or "OTHERS"
                dimension = f"Item ID: {value}"

        print(f"  {type_str:12} {negative_str:12} {dimension}")

except Exception as e:
    print(f"❌ Error reading tree: {e}")

print("\n" + "="*60)
print("Now testing rebuild_tree_with_label_and_item_ids...")
print("="*60 + "\n")

# Test item IDs to add as exclusions
test_item_ids = ["TEST123", "TEST456", "TEST789"]

print(f"Adding {len(test_item_ids)} test item ID exclusions: {test_item_ids}\n")

# Run the rebuild function
try:
    rebuild_tree_with_label_and_item_ids(
        client=client,
        customer_id=customer_id,
        ad_group_id=ad_group_id,
        ad_group_name=ad_group_name,
        item_ids=test_item_ids,
        default_bid_micros=200_000
    )

    print("\n" + "="*60)
    print("✅ Tree rebuild completed successfully!")
    print("="*60)

except Exception as e:
    print(f"\n❌ Error during rebuild: {e}")
    import traceback
    traceback.print_exc()

# Read the tree again to verify exclusions were preserved
print("\n=== Reading tree structure AFTER rebuild ===\n")

try:
    results = list(ga_service.search(customer_id=customer_id, query=query))
    print(f"Found {len(results)} listing group criteria:\n")

    custom_label_exclusions = []
    item_id_exclusions = []

    for row in results:
        criterion = row.ad_group_criterion
        lg = criterion.listing_group
        case_val = lg.case_value

        negative_str = "[NEGATIVE]" if criterion.negative else "[POSITIVE]"
        type_str = lg.type_.name

        dimension = "ROOT"
        if case_val:
            dim_type = case_val._pb.WhichOneof("dimension")
            if dim_type == "product_custom_attribute":
                index = case_val.product_custom_attribute.index.name
                value = case_val.product_custom_attribute.value or "OTHERS"
                dimension = f"Custom Attr {index[-1]}: {value}"
                if criterion.negative and value != "OTHERS":
                    custom_label_exclusions.append(f"{index}: {value}")
            elif dim_type == "product_item_id":
                value = case_val.product_item_id.value or "OTHERS"
                dimension = f"Item ID: {value}"
                if criterion.negative and value != "OTHERS":
                    item_id_exclusions.append(value)

        print(f"  {type_str:12} {negative_str:12} {dimension}")

    print("\n" + "="*60)
    print("SUMMARY:")
    print("="*60)
    print(f"Custom Label Exclusions: {len(custom_label_exclusions)}")
    for excl in custom_label_exclusions:
        print(f"  - {excl}")
    print(f"\nItem ID Exclusions: {len(item_id_exclusions)}")
    for excl in item_id_exclusions[:10]:  # Show first 10
        print(f"  - {excl}")
    if len(item_id_exclusions) > 10:
        print(f"  ... and {len(item_id_exclusions) - 10} more")

except Exception as e:
    print(f"❌ Error reading final tree: {e}")

print("\n✅ Test completed!")
