#!/usr/bin/env python3
"""Test script to verify both tree patterns work correctly"""

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

print("="*80)
print("PATTERN 1 TEST: Single label with custom label exclusions")
print("Ad Group: 144284844193 (A)")
print("="*80)

try:
    rebuild_tree_with_label_and_item_ids(
        client=client,
        customer_id=customer_id,
        ad_group_id=144284844193,
        ad_group_name='A',
        item_ids=['PATTERN1_TEST1', 'PATTERN1_TEST2'],
        default_bid_micros=100_000
    )
    print("\n✅ Pattern 1 test completed")
except Exception as e:
    print(f"\n❌ Pattern 1 test failed: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*80)
print("PATTERN 2 TEST: Multiple label subdivisions")
print("Ad Group: 167597626207 (No Data)")
print("="*80)

try:
    rebuild_tree_with_label_and_item_ids(
        client=client,
        customer_id=customer_id,
        ad_group_id=167597626207,
        ad_group_name='No Data',
        item_ids=['PATTERN2_TEST1', 'PATTERN2_TEST2'],
        default_bid_micros=100_000
    )
    print("\n✅ Pattern 2 test completed")
except Exception as e:
    print(f"\n❌ Pattern 2 test failed: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*80)
print("All tests completed!")
print("="*80)
