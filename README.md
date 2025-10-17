# Tag Toppers - Google Shopping Campaign Automation

This script automates the creation and management of Google Shopping campaigns with specific item ID targeting.

## Overview

The script creates two types of campaigns:
1. **Existing campaigns**: Updates product partition trees with label-based filtering and negative Item ID exclusions
2. **Tag-toppers campaigns**: Creates new campaigns that ONLY show specific Item IDs from a spreadsheet

## Features

- Reads Item IDs from Google Sheets
- Creates shopping campaigns with custom product partition trees
- Supports label-based filtering (a, b, c, no data, no ean)
- Implements both inclusive and exclusive Item ID targeting
- Automatic duplicate removal
- Concurrent modification protection with strategic delays

## Requirements

- Python 3.10+
- Google Ads API credentials
- Google Sheets API credentials (service account)
- Required Python packages:
  - google-ads
  - google-api-python-client
  - google-auth-httplib2
  - google-auth-oauthlib

## Configuration

Create a `creds` file in the script directory with the following environment variables:
```
GOOGLE_CLIENT_ID=your_client_id
GOOGLE_CLIENT_SECRET=your_client_secret
GOOGLE_REFRESH_TOKEN=your_refresh_token
GOOGLE_DEVELOPER_TOKEN=your_developer_token
GOOGLE_LOGIN_CUSTOMER_ID=your_login_customer_id
```

Alternatively, set these as environment variables before running the script.

Place your service account JSON file at the path specified in the script for Google Sheets access.

## Recent Fixes

### Regex Bug Fix (2025-10-17)
Fixed a critical bug where the regex pattern `r"[;,|\\s]+"` was splitting Item IDs on the letter 's', causing 160 IDs to be incorrectly parsed as 229 fragments. Changed to `r"[;,|\s]+"` to properly match whitespace characters.

### Concurrent Modification Protection (2025-10-17)
Added strategic `time.sleep()` delays at critical points:
- 2 seconds after campaign creation
- 1 second after ad group creation
- 0.5 seconds between product partition tree mutations
- 1 second after tree rebuild before creating shopping ads

## Usage

```bash
python GSD_tagtoppers.py
```

The script will:
1. Read Item IDs from the configured Google Sheets spreadsheet
2. Find or create campaigns for each shop
3. Update existing campaigns with negative Item ID targeting
4. Create tag_toppers campaigns with positive Item ID targeting

## License

Internal use only
