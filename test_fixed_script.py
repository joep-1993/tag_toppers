#!/usr/bin/env python3
"""Test script to verify custom label exclusions are preserved"""

import os
from google.ads.googleads.client import GoogleAdsClient
from listing_tree import rebuild_tree_with_label_and_item_ids

# Load credentials
def load_credentials():
    creds = {}
    creds_file = 'creds'
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

google_ads_config = {
    'developer_token': creds['developer_token'],
    'refresh_token': creds['refresh_token'],
    'client_id': creds['client_id'],
    'client_secret': creds['client_secret'],
    'login_customer_id': creds['login_customer_id'],
    'use_proto_plus': True,
}
client = GoogleAdsClient.load_from_dict(google_ads_config)

customer_id = '7938980174'
ad_group_id = 144284844193
ad_group_name = 'A'

print("="*70)
print("Testing rebuild_tree_with_label_and_item_ids")
print("="*70)

# Test with 3 new item IDs
test_item_ids = ['TEST_ITEM_1', 'TEST_ITEM_2', 'TEST_ITEM_3']

print(f"\nAdding {len(test_item_ids)} test item ID exclusions")
print(f"Expected behavior: Preserve custom label 4 exclusions (8-13, 0-8)\n")

try:
    rebuild_tree_with_label_and_item_ids(
        client=client,
        customer_id=customer_id,
        ad_group_id=ad_group_id,
        ad_group_name=ad_group_name,
        item_ids=test_item_ids,
        default_bid_micros=100_000  # €0.10
    )
    print("\n✅ Script completed successfully!")
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()

# Read final tree
print("\n" + "="*70)
print("Final tree structure:")
print("="*70 + "\n")

ga_service = client.get_service('GoogleAdsService')
ag_service = client.get_service('AdGroupService')
ag_path = ag_service.ad_group_path(customer_id, ad_group_id)

query = f'''
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
'''

results = list(ga_service.search(customer_id=customer_id, query=query))

custom_label_4_exclusions = []
item_id_exclusions = []

for row in results:
    criterion = row.ad_group_criterion
    lg = criterion.listing_group
    case_val = lg.case_value

    negative_str = '[NEGATIVE]' if criterion.negative else '[POSITIVE]'
    type_str = lg.type_.name
    bid = f'€{criterion.cpc_bid_micros/1000000:.2f}' if criterion.cpc_bid_micros else 'no bid'

    dimension = 'ROOT'
    if case_val:
        dim_type = case_val._pb.WhichOneof('dimension')
        if dim_type == 'product_custom_attribute':
            index = case_val.product_custom_attribute.index.name
            value = case_val.product_custom_attribute.value or 'OTHERS'
            dimension = f'Custom Attr {index[-1]}: {value}'
            if criterion.negative and index == 'INDEX4' and value not in ['OTHERS', '']:
                custom_label_4_exclusions.append(value)
        elif dim_type == 'product_item_id':
            value = case_val.product_item_id.value or 'OTHERS'
            dimension = f'Item ID: {value}'
            if criterion.negative and value not in ['OTHERS', '']:
                item_id_exclusions.append(value)

    print(f'{type_str:12} {negative_str:12} {bid:10} {dimension}')

print("\n" + "="*70)
print("VERIFICATION:")
print("="*70)
print(f"\n✓ Custom Label 4 exclusions preserved: {len(custom_label_4_exclusions)}")
for excl in custom_label_4_exclusions:
    print(f"  - {excl}")

print(f"\n✓ Item ID exclusions added: {len(item_id_exclusions)}")
for excl in item_id_exclusions[:5]:
    print(f"  - {excl}")
if len(item_id_exclusions) > 5:
    print(f"  ... and {len(item_id_exclusions) - 5} more")

expected_custom_label_exclusions = ['8-13', '0-8']
if set(custom_label_4_exclusions) == set(expected_custom_label_exclusions):
    print(f"\n🎉 SUCCESS! Custom label 4 exclusions preserved correctly!")
else:
    print(f"\n⚠️ WARNING: Expected {expected_custom_label_exclusions}, got {custom_label_4_exclusions}")
