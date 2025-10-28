# GSD tag-toppers (ONLY specific item IDs)
# -------------------------------------------------------------
# Deze versie maakt een product partitie boom met INCLUSIEVE logica:
# Laat ALLEEN specifieke item IDs zien uit de spreadsheet
#
# Root SUBDIVISION
# ├─ Item ID OTHERS [NEGATIVE] → Blokkeert alle items behalve specifieke IDs
# └─ Specifieke Item IDs [POSITIVE, €0.20] → Laat alleen deze items zien
#
# Voorwaarden in Merchant Center:
# - Item IDs in spreadsheet (kolom F) worden GETOOND (positief)
# - Alle andere items worden geblokkeerd
#
# Logica: Laat ALLEEN specifieke item IDs zien, blokkeer de rest.
# -------------------------------------------------------------

import time
import json
import re
import os

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
from googleapiclient.discovery import build
from google.oauth2 import service_account

# Import listing tree function
from listing_tree import rebuild_tree_with_label_and_item_ids

# =========================
# OAuth / Config
# =========================

refresh_token = os.getenv("GOOGLE_REFRESH_TOKEN", "your-refresh-token-here")
developer_token = os.getenv("GOOGLE_DEVELOPER_TOKEN", "your-developer-token-here")
login_customer_id = os.getenv("GOOGLE_LOGIN_CUSTOMER_ID", "your-login-customer-id")

def load_google_oauth_from_env():
    # First try environment variables
    cid = os.getenv("GOOGLE_CLIENT_ID")
    cs  = os.getenv("GOOGLE_CLIENT_SECRET")

    # If not found, try loading from creds file
    if not cid or not cs:
        creds_file = os.path.join(os.path.dirname(__file__), 'creds')
        if os.path.exists(creds_file):
            with open(creds_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('GOOGLE_CLIENT_ID='):
                        cid = line.split('=', 1)[1]
                    elif line.startswith('GOOGLE_CLIENT_SECRET='):
                        cs = line.split('=', 1)[1]

    missing = []
    if not cid: missing.append("GOOGLE_CLIENT_ID")
    if not cs:  missing.append("GOOGLE_CLIENT_SECRET")
    if missing:
        raise RuntimeError(
            "Environment variables ontbreken: "
            + ", ".join(missing)
            + ".\nZet deze in het 'creds' bestand of als environment variables."
        )
    return cid, cs

client_id, client_secret = load_google_oauth_from_env()

# Google Ads client (OAuth via refresh token)
google_ads_config = {
    "developer_token": developer_token,
    "refresh_token":  refresh_token,
    "client_id":      client_id,
    "client_secret":  client_secret,
    "login_customer_id": login_customer_id,
    "use_proto_plus": True,
}
client = GoogleAdsClient.load_from_dict(google_ads_config)

# Optioneel: los access token verversen (handig voor sanity check)
creds = Credentials(
    token=None,
    refresh_token=refresh_token,
    token_uri="https://oauth2.googleapis.com/token",
    client_id=client_id,
    client_secret=client_secret,
)
creds.refresh(Request())
print("✅ Access token:", (creds.token or "")[:20], "...")

# Service account voor Google Sheets / Merchant Center
# Auto-detect Windows vs WSL path
if os.name == 'nt':  # Windows
    SERVICE_ACCOUNT_FILE = r'C:\Users\JoepvanSchagen\Downloads\Python\gsd-campaign-creation.json'
else:  # WSL/Linux
    SERVICE_ACCOUNT_FILE = '/mnt/c/Users/JoepvanSchagen/Downloads/Python/gsd-campaign-creation.json'

# =========================
# Accounts / constants
# =========================

customer_id_nl = '7938980174'
customer_id_be = '2454295509'
customer_id_de = '4192567576'

mc_id_de = '5342886105'
mc_id_nl = '5592708765'
mc_id_be = '5588879919'

tracking_template_nl = 'https://www.beslist.nl/outclick/redirect?aff_id=900&params=productId%3D{product_id}%26marketingChannelId%3D14&url={lpurl}'
tracking_template_be = 'https://www.beslist.be/outclick/redirect?aff_id=901&params=productId%3D{product_id}%26marketingChannelId%3D14&url={lpurl}'
tracking_template_de = 'https://www.shopcaddy.de/outclick/redirect?aff_id=910&params=productId%3D{product_id}%26marketingChannelId%3D14&url={lpurl}'

last_criterion_id = 0
script_label = "TAGTOPPERS_SCRIPT"

# =========================
# Utilities
# =========================

def ensure_campaign_label_exists(client, customer_id, label_name):
    google_ads_service = client.get_service("GoogleAdsService")
    label_service = client.get_service("LabelService")

    query = f"""
    SELECT label.resource_name, label.name
    FROM label
    WHERE label.name = '{label_name}'
    """
    response = google_ads_service.search(customer_id=customer_id, query=query)
    for row in response:
        return row.label.resource_name

    # Label bestaat nog niet, dus aanmaken
    label_operation = client.get_type("LabelOperation")
    label = label_operation.create
    label.name = label_name

    try:
        label_response = label_service.mutate_labels(
            customer_id=customer_id, operations=[label_operation]
        )
        return label_response.results[0].resource_name
    except GoogleAdsException as ex:
        print(f'error: {ex}')
        return None

def create_location_op(client, customer_id, campaign_id, country):
    campaign_service = client.get_service("CampaignService")
    geo_target_constant_service = client.get_service("GeoTargetConstantService")

    if country == "NL":
        location_id = "2528"
    elif country == "BE":
        location_id = "2056"
    elif country == "DE":
        location_id = "2276"

    # Create the campaign criterion.
    campaign_criterion_operation = client.get_type("CampaignCriterionOperation")
    campaign_criterion = campaign_criterion_operation.create
    campaign_criterion.campaign = campaign_service.campaign_path(
        customer_id, campaign_id
    )

    # Besides using location_id, you can also search by location names from
    # GeoTargetConstantService.suggest_geo_target_constants() and directly
    # apply GeoTargetConstant.resource_name here. An example can be found
    # in get_geo_target_constant_by_names.py.
    campaign_criterion.location.geo_target_constant = (
        geo_target_constant_service.geo_target_constant_path(location_id)
    )

    return campaign_criterion_operation

def add_standard_shopping_campaign(
    client, customer_id, merchant_center_account_id, campaign_name, budget_name,
    tracking_template, country, shopid, shopname, label, budget, final_url_suffix=None
):
    campaign_service = client.get_service("CampaignService")
    google_ads_service = client.get_service("GoogleAdsService")

    # Bestaat al?
    query = f""" 
    SELECT campaign.id, campaign.resource_name, campaign.status 
    FROM campaign 
    WHERE campaign.name LIKE '%shop_id:{shopid}]%' 
    AND campaign.name LIKE '%shop:{shopname}%' 
    AND campaign.name LIKE '%label:{label}%' 
    """
    response = google_ads_service.search(customer_id=customer_id, query=query)
    for row in response:
        if row.campaign.status != client.enums.CampaignStatusEnum.REMOVED:
            print(f"                Campaign '{campaign_name}' already exists with ID {row.campaign.id}")
            return row.campaign.resource_name

    # Budget (niet gedeeld)
    campaign_budget_service = client.get_service("CampaignBudgetService")
    campaign_budget_operation = client.get_type("CampaignBudgetOperation")
    campaign_budget = campaign_budget_operation.create
    campaign_budget.name = budget_name
    campaign_budget.delivery_method = client.enums.BudgetDeliveryMethodEnum.STANDARD
    campaign_budget.amount_micros = budget  # bv. 5_000_000 = €5/dag
    campaign_budget.explicitly_shared = False
    try:
        campaign_budget_response = campaign_budget_service.mutate_campaign_budgets(
            customer_id=customer_id, operations=[campaign_budget_operation]
        )
    except GoogleAdsException as ex:
        print(f"Failed to create budget: {ex}")
        return None

    # Campaign
    campaign_operation = client.get_type("CampaignOperation")
    campaign = campaign_operation.create
    campaign.name = campaign_name
    campaign.advertising_channel_type = client.enums.AdvertisingChannelTypeEnum.SHOPPING
    campaign.shopping_setting.merchant_id = int(merchant_center_account_id)
    campaign.shopping_setting.campaign_priority = 0
    campaign.shopping_setting.enable_local = True
    campaign.tracking_url_template = tracking_template
    campaign.contains_eu_political_advertising = (
        client.enums.EuPoliticalAdvertisingStatusEnum.DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING
    )
    if final_url_suffix:
        campaign.final_url_suffix = final_url_suffix
    campaign.status = client.enums.CampaignStatusEnum.PAUSED
    campaign.manual_cpc.enhanced_cpc_enabled = False
    campaign.campaign_budget = campaign_budget_response.results[0].resource_name

    try:
        campaign_response = campaign_service.mutate_campaigns(
            customer_id=customer_id, operations=[campaign_operation]
        )
    except GoogleAdsException as ex:
        print(f"Failed to create campaign '{campaign_name}': {ex}")
        # probeer alsnog de resource van een bestaande te vinden
        response_retry = google_ads_service.search(customer_id=customer_id, query=query)
        for row in response_retry:
            if row.campaign.status != client.enums.CampaignStatusEnum.REMOVED:
                print(f"Campaign '{campaign_name}' gevonden na fout bij aanmaken.")
                return row.campaign.resource_name
        print(f"Kan campagne '{campaign_name}' niet aanmaken en geen actieve campagne gevonden.")
        return None

    campaign_resource_name = campaign_response.results[0].resource_name

    # Add location targeting
    campaign_id = campaign_resource_name.split("/")[-1]
    campaign_criterion_service = client.get_service("CampaignCriterionService")
    operations = [
        create_location_op(client, customer_id, campaign_id, country),
    ]
    try:
        campaign_criterion_service.mutate_campaign_criteria(
            customer_id=customer_id, operations=operations
        )
    except GoogleAdsException as ex:
        #handle_googleads_exception(ex)
        print(f'error: {ex}')

    # Label toevoegen
    campaign_label_service = client.get_service("CampaignLabelService")
    label_resource_name = ensure_campaign_label_exists(client, customer_id, script_label)
    if label_resource_name:
        campaign_label_operation = client.get_type("CampaignLabelOperation")
        campaign_label = campaign_label_operation.create
        campaign_label.campaign = campaign_resource_name
        campaign_label.label = label_resource_name
        try:
            campaign_label_service.mutate_campaign_labels(
                customer_id=customer_id, operations=[campaign_label_operation]
            )
        except GoogleAdsException as ex:
            print(f'error (label): {ex}')

    print(f"                Standard shopping campaign created (and labeled): {campaign_name}")
    time.sleep(2)  # Wait for campaign to propagate
    return campaign_resource_name

def create_ad_group_basic(client, customer_id: str, campaign_resource_name: str, ad_group_name: str, bid_micros: int = 200_000):
    ad_group_service = client.get_service("AdGroupService")
    op = client.get_type("AdGroupOperation")
    ag = op.create
    ag.campaign = campaign_resource_name
    ag.name = ad_group_name
    ag.cpc_bid_micros = bid_micros
    ag.status = client.enums.AdGroupStatusEnum.ENABLED
    resp = ad_group_service.mutate_ad_groups(customer_id=customer_id, operations=[op])
    time.sleep(1)  # Wait for ad group to propagate
    return resp.results[0].resource_name

def get_or_create_tag_toppers_adgroup(client, customer_id, campaign_resource, name="tag_toppers", bid_micros=200_000):
    """Zoekt ad group op naam binnen campagne. Maakt 'm alleen aan als hij niet bestaat."""
    ga = client.get_service("GoogleAdsService")
    q = f"""
      SELECT ad_group.resource_name, ad_group.id, ad_group.name, ad_group.status
      FROM ad_group
      WHERE ad_group.campaign = '{campaign_resource}'
        AND ad_group.name = '{name}'
        AND ad_group.status != 'REMOVED'
      LIMIT 1
    """
    res = ga.search(customer_id=customer_id, query=q)
    for row in res:
        print(f"                        Ad group bestaat al: {row.ad_group.id} ({row.ad_group.name})")
        return row.ad_group.resource_name

    # niet gevonden → aanmaken
    return create_ad_group_basic(client, customer_id, campaign_resource, name, bid_micros)

def add_shopping_product_ad_group_ad(client, customer_id, ad_group_resource):
    ad_group_ad_service = client.get_service("AdGroupAdService")
    google_ads_service = client.get_service("GoogleAdsService")

    query = f"""
        SELECT ad_group_ad.ad.id, ad_group_ad.resource_name, ad_group_ad.status
        FROM ad_group_ad
        WHERE ad_group_ad.ad_group = '{ad_group_resource}'
    """
    response = google_ads_service.search(customer_id=customer_id, query=query)
    for row in response:
        if row.ad_group_ad.status != client.enums.AdGroupAdStatusEnum.REMOVED:
            print(f"                                Ad already exists in ad group '{ad_group_resource}' with ID {row.ad_group_ad.ad.id}")
            return row.ad_group_ad.resource_name

    # Nieuw
    ad_group_ad_operation = client.get_type("AdGroupAdOperation")
    ad_group_ad = ad_group_ad_operation.create
    ad_group_ad.ad_group = ad_group_resource
    ad_group_ad.status = client.enums.AdGroupAdStatusEnum.ENABLED
    client.copy_from(
        ad_group_ad.ad.shopping_product_ad,
        client.get_type("ShoppingProductAdInfo"),
    )
    ad_group_ad_response = ad_group_ad_service.mutate_ad_group_ads(
        customer_id=customer_id, operations=[ad_group_ad_operation]
    )
    ad_group_ad_resource_name = ad_group_ad_response.results[0].resource_name
    print(f"                                Created new shopping product ad in ad group '{ad_group_resource}'")
    return ad_group_ad_resource_name

# =========================
# Listing group helpers
# =========================

def next_id():
    global last_criterion_id
    last_criterion_id -= 1
    return str(last_criterion_id)

def create_listing_group_subdivision(
    client,
    customer_id,
    ad_group_id,
    parent_ad_group_criterion_resource_name=None,
    listing_dimension_info=None,
):
    operation = client.get_type("AdGroupCriterionOperation")
    ad_group_criterion = operation.create
    ad_group_criterion.resource_name = client.get_service(
        "AdGroupCriterionService"
    ).ad_group_criterion_path(customer_id, ad_group_id, next_id())
    ad_group_criterion.status = client.enums.AdGroupCriterionStatusEnum.ENABLED

    listing_group_info = ad_group_criterion.listing_group
    listing_group_info.type_ = client.enums.ListingGroupTypeEnum.SUBDIVISION
    if parent_ad_group_criterion_resource_name is not None:
        listing_group_info.parent_ad_group_criterion = parent_ad_group_criterion_resource_name
    if listing_dimension_info is not None:
        client.copy_from(listing_group_info.case_value, listing_dimension_info)
    return operation

def create_listing_group_unit_biddable(
        client,
        customer_id,
        ad_group_id,
        parent_ad_group_criterion_resource_name,
        listing_dimension_info,
        targeting_negative,
        cpc_bid_micros=None
):
    operation = client.get_type("AdGroupCriterionOperation")
    criterion = operation.create
    criterion.resource_name = client.get_service(
        "AdGroupCriterionService"
    ).ad_group_criterion_path(customer_id, ad_group_id, next_id())
    criterion.status = client.enums.AdGroupCriterionStatusEnum.ENABLED
    if cpc_bid_micros and targeting_negative == False:
        criterion.cpc_bid_micros = cpc_bid_micros

    listing_group = criterion.listing_group
    listing_group.type_ = client.enums.ListingGroupTypeEnum.UNIT
    listing_group.parent_ad_group_criterion = parent_ad_group_criterion_resource_name

    # Case values contain the listing dimension used for the node.
    # For OTHERS units, pass a ListingDimensionInfo with index but no value
    if listing_dimension_info is not None:
        client.copy_from(listing_group.case_value, listing_dimension_info)

    if targeting_negative:
        criterion.negative = True
    return operation

def _clean_shopname(name: str) -> str:
    return name.split("|")[0].strip() if name else name

def find_campaigns_for_shop(client, customer_id: str, shopid: str, shopname: str):
    ga = client.get_service("GoogleAdsService")
    q = f"""
        SELECT campaign.id, campaign.name, campaign.resource_name, campaign.status
        FROM campaign
        WHERE campaign.name LIKE '%shop_id:{shopid}]%'
          AND campaign.name LIKE '%shop:{_clean_shopname(shopname)}%'
          AND campaign.status != 'REMOVED'
    """
    res = ga.search(customer_id=customer_id, query=q)
    return [(row.campaign.id, row.campaign.name, row.campaign.resource_name) for row in res]

def list_ad_groups_in_campaign(client, customer_id: str, campaign_resource_name: str):
    ga = client.get_service("GoogleAdsService")
    q = f"""
        SELECT ad_group.id, ad_group.resource_name, ad_group.name, ad_group.status
        FROM ad_group
        WHERE ad_group.campaign = '{campaign_resource_name}'
          AND ad_group.status != 'REMOVED'
    """
    res = ga.search(customer_id=customer_id, query=q)
    return [(row.ad_group.id, row.ad_group.resource_name, row.ad_group.name) for row in res]

def get_merchant_id_for_campaign(customer_id, shop_id):
    try:
        ga_service = client.get_service("GoogleAdsService")
        query = f"""
            SELECT 
                campaign.id, 
                campaign.name, 
                campaign.status, 
                campaign.shopping_setting.merchant_id
            FROM campaign
            WHERE campaign.name LIKE '%{shop_id}]%'
        """
        response = ga_service.search(customer_id=customer_id, query=query)
        for row in response:
            return row.campaign.shopping_setting.merchant_id
        return None
    except GoogleAdsException as ex:
        print(f"❌ Google Ads API error (get_merchant_id_for_campaign): {ex.failure}")
        return None

# --- Safe removal helpers (units -> subs) ---
def list_listing_groups_with_depth(client, customer_id: str, ad_group_id: str):
    ga = client.get_service("GoogleAdsService")
    ag_path = client.get_service("AdGroupService").ad_group_path(customer_id, ad_group_id)
    q = f"""
      SELECT
        ad_group_criterion.resource_name,
        ad_group_criterion.listing_group.type,
        ad_group_criterion.listing_group.parent_ad_group_criterion
      FROM ad_group_criterion
      WHERE ad_group_criterion.ad_group = '{ag_path}'
        AND ad_group_criterion.type = 'LISTING_GROUP'
    """
    rows = list(ga.search(customer_id=customer_id, query=q))
    by_res = {r.ad_group_criterion.resource_name: r for r in rows}
    depth = {}
    def get_depth(res):
        if res in depth:
            return depth[res]
        parent = by_res[res].ad_group_criterion.listing_group.parent_ad_group_criterion
        d = 0 if not parent else 1 + get_depth(parent)
        depth[res] = d
        return d
    for r in rows:
        get_depth(r.ad_group_criterion.resource_name)
    return rows, depth

def safe_remove_entire_listing_tree(client, customer_id: str, ad_group_id: str):
    agc = client.get_service("AdGroupCriterionService")
    rows, depth = list_listing_groups_with_depth(client, customer_id, ad_group_id)
    if not rows:
        return

    # Find the root SUBDIVISION (the one with no parent)
    root = None
    for r in rows:
        if not r.ad_group_criterion.listing_group.parent_ad_group_criterion:
            root = r
            break

    if not root:
        return

    # Remove only the root - the API will cascade-delete all children
    op = client.get_type("AdGroupCriterionOperation")
    op.remove = root.ad_group_criterion.resource_name

    try:
        agc.mutate_ad_group_criteria(customer_id=customer_id, operations=[op])
    except GoogleAdsException as ex:
        # Ignore if the tree is already gone or resource not found
        if not any(
            (getattr(e.error_code, "criterion_error", None) and
             e.error_code.criterion_error.name == "LISTING_GROUP_DOES_NOT_EXIST") or
            (getattr(e.error_code, "mutate_error", None) and
             e.error_code.mutate_error.name == "RESOURCE_NOT_FOUND")
            for e in ex.failure.errors
        ):
            raise


# -------- ONLY specific Item IDs (INCLUDE logic - for tag_toppers campaigns) --------
def rebuild_tree_with_specific_item_ids(
    client,
    customer_id: str,
    ad_group_id: int,
    item_ids=None,                 # list of item IDs to INCLUDE (positive targeting)
    default_bid_micros: int = 200_000
):
    """
    Creates tree structure with INCLUSIVE logic:
    Root SUBDIVISION
    ├─ Item ID OTHERS [NEGATIVE] → Blocks all items except specific IDs
    └─ Specific Item IDs [POSITIVE, biddable] → Show only these items

    This uses INCLUSIVE logic: ONLY show specific IDs, block everything else.
    """
    if item_ids is None:
        item_ids = []

    # CRITICAL FIX: Ensure item_ids is a list, not a string
    # If it's a string, iterating over it gives individual characters!
    if isinstance(item_ids, str):
        print(f"⚠️ WARNING: item_ids was a string, not a list! Converting...")
        print(f"   String value: '{item_ids[:100]}...'")
        # Try to parse it as comma-separated
        import re
        splitter = re.compile(r"[;,|\s]+")
        item_ids = [p.strip() for p in splitter.split(item_ids) if p.strip()]
        print(f"   Converted to list with {len(item_ids)} items")

    if not item_ids:
        print("⚠️ No item IDs provided - skipping tree rebuild")
        return

    # 1) Oude boom veilig verwijderen
    safe_remove_entire_listing_tree(client, customer_id, str(ad_group_id))

    agc = client.get_service("AdGroupCriterionService")

    # MUTATE 1: Create root SUBDIVISION + Item ID OTHERS (negative)
    ops1 = []

    # 1. ROOT SUBDIVISION (no case_value - root is always just "everything")
    root_op = create_listing_group_subdivision(
        client=client,
        customer_id=customer_id,
        ad_group_id=str(ad_group_id),
        parent_ad_group_criterion_resource_name=None,
        listing_dimension_info=None  # Root has no dimension
    )
    root_tmp = root_op.create.resource_name
    ops1.append(root_op)

    # 2. Item ID OTHERS (negative - blocks everything except specific IDs)
    dim_itemid_others = client.get_type("ListingDimensionInfo")
    client.copy_from(
        dim_itemid_others.product_item_id,
        client.get_type("ProductItemIdInfo"),
    )
    # Don't set value - OTHERS case
    ops1.append(
        create_listing_group_unit_biddable(
            client=client,
            customer_id=customer_id,
            ad_group_id=str(ad_group_id),
            parent_ad_group_criterion_resource_name=root_tmp,
            listing_dimension_info=dim_itemid_others,
            targeting_negative=True,  # NEGATIVE - blocks everything else
            cpc_bid_micros=None
        )
    )

    # Execute first mutate
    resp1 = agc.mutate_ad_group_criteria(customer_id=customer_id, operations=ops1)
    root_actual = resp1.results[0].resource_name
    time.sleep(0.5)  # Wait for criteria to propagate

    # MUTATE 2: Add specific Item IDs as POSITIVE units (to show only them)
    ops2 = []

    # Deduplicate the list to avoid LISTING_GROUP_ALREADY_EXISTS errors
    unique_item_ids = list(dict.fromkeys(item_ids))  # Preserves order while deduplicating

    # Debug: Print IDs being sent to Google Ads
    print(f"DEBUG: Sending {len(unique_item_ids)} unique Item IDs to Google Ads:")
    for idx, item_id in enumerate(unique_item_ids[:5], 1):  # Show first 5
        print(f"  {idx}. '{item_id}' (length: {len(str(item_id))})")
    if len(unique_item_ids) > 5:
        print(f"  ... and {len(unique_item_ids) - 5} more")

    for item_id in unique_item_ids:
        dim_item = client.get_type("ListingDimensionInfo")
        dim_item.product_item_id.value = str(item_id)
        ops2.append(
            create_listing_group_unit_biddable(
                client=client,
                customer_id=customer_id,
                ad_group_id=str(ad_group_id),
                parent_ad_group_criterion_resource_name=root_actual,
                listing_dimension_info=dim_item,
                targeting_negative=False,  # POSITIVE targeting
                cpc_bid_micros=default_bid_micros
            )
        )

    if ops2:
        agc.mutate_ad_group_criteria(customer_id=customer_id, operations=ops2)
        unique_count = len(unique_item_ids)
        total_count = len(item_ids)
        if total_count > unique_count:
            print(f"✅ Tree rebuilt: ONLY show {unique_count} unique Item IDs ({total_count-unique_count} duplicates removed), block all others.")
        else:
            print(f"✅ Tree rebuilt: ONLY show {unique_count} Item IDs, block all others.")

# =========================
# Spreadsheet I/O (tag_toppers input)
# =========================

def mark_rows_as_processed(
    row_numbers: list,
    spreadsheet_id: str = "1m4k8kxhfU7oLIAH3DJOyYx_PKSv4luPyX97j45Wa6s4",
    worksheet_name: str = "tag_toppers",
    column: str = "G"  # Column G is the "processed" flag column
):
    """
    Marks rows as processed by setting the specified column to TRUE.
    More efficient to call once with all row numbers after processing is complete.

    Args:
        row_numbers: List of row numbers to mark as processed (1-indexed)
        spreadsheet_id: Google Sheets spreadsheet ID
        worksheet_name: Name of the worksheet/tab
        column: Column letter to update (default: G)
    """
    if not row_numbers:
        return

    service_account_file = SERVICE_ACCOUNT_FILE
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]  # Need write permission
    creds = service_account.Credentials.from_service_account_file(service_account_file, scopes=scopes)
    service = build("sheets", "v4", credentials=creds)
    sheet = service.spreadsheets()

    # Build batch update data
    data = []
    for row_num in row_numbers:
        data.append({
            "range": f"{worksheet_name}!{column}{row_num}",
            "values": [["TRUE"]]
        })

    body = {
        "valueInputOption": "RAW",
        "data": data
    }

    try:
        result = sheet.values().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body=body
        ).execute()
        updated_cells = result.get('totalUpdatedCells', 0)
        print(f"✅ Marked {len(row_numbers)} row(s) as processed in column {column} ({updated_cells} cells updated)")
    except Exception as e:
        print(f"❌ Error updating spreadsheet: {e}")
        print(f"   Make sure the service account has edit access to the spreadsheet!")
        import traceback
        traceback.print_exc()


def get_spreadsheet_input(
    spreadsheet_id: str = "1m4k8kxhfU7oLIAH3DJOyYx_PKSv4luPyX97j45Wa6s4",
    worksheet_name: str = "tag_toppers",
    return_json: bool = True
):
    service_account_file = SERVICE_ACCOUNT_FILE
    scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    creds = service_account.Credentials.from_service_account_file(service_account_file, scopes=scopes)
    service = build("sheets", "v4", credentials=creds)
    sheet = service.spreadsheets()

    rng = f"{worksheet_name}!A:G"
    resp = sheet.values().get(spreadsheetId=spreadsheet_id, range=rng).execute()
    rows = resp.get("values", [])

    if not rows:
        return "[] " if return_json else []

    last_filled_row_a = 0
    for i, r in enumerate(rows, start=1):
        if len(r) >= 1 and str(r[0]).strip() != "":
            last_filled_row_a = i
    if last_filled_row_a == 0:
        return "[] " if return_json else []

    def is_true(val):
        if isinstance(val, bool):
            return val is True
        s = str(val).strip().upper()
        return s in {"TRUE", "WAAR", "1"}
    last_true_row_g = 0
    for i, r in enumerate(rows, start=1):
        if len(r) >= 7 and is_true(r[6]):
            last_true_row_g = i

    start_row = (last_true_row_g + 1) if last_true_row_g > 0 else 2
    if start_row > last_filled_row_a:
        return "[] " if return_json else []

    splitter = re.compile(r"[;,|\s]+")
    def parse_item_ids(cell_val):
        if cell_val is None or str(cell_val).strip() == "":
            return []
        parts = [p.strip() for p in splitter.split(str(cell_val)) if p.strip() != ""]
        return parts

    results = []
    for i in range(start_row, last_filled_row_a + 1):
        r = rows[i - 1] if i - 1 < len(rows) else []
        shop_id   = r[1].strip() if len(r) > 1 else ""
        shop_name = r[2].strip() if len(r) > 2 else ""
        domain    = r[4].strip() if len(r) > 4 else ""

        # DEBUG: Check the raw cell value
        raw_cell = r[5] if len(r) > 5 else ""
        item_ids  = parse_item_ids(raw_cell)  # Item IDs to INCLUDE (positive targeting)

        # DEBUG: Print extraction details for first shop
        if len(results) == 0 and item_ids:
            print(f"\n=== DEBUG: Spreadsheet extraction (row {i}) ===")
            print(f"Shop: {shop_name} (ID: {shop_id})")
            print(f"Raw cell value (first 200 chars): '{raw_cell[:200]}'...")
            print(f"Parsed to {len(item_ids)} IDs")
            print(f"First 5 IDs:")
            for idx, item_id in enumerate(item_ids[:5], 1):
                print(f"  {idx}. '{item_id}' (length: {len(item_id)})")
            print(f"item_ids type: {type(item_ids)}")
            print("=" * 50 + "\n")

        if shop_id or shop_name:
            results.append({
                "row": i,
                "shop_id": shop_id,
                "shop_name": shop_name,
                "domain": domain,
                "item_ids": item_ids,
            })

    return json.dumps(results, ensure_ascii=False) if return_json else results

# =========================
# Tag-toppers campaign creation (label + item ID based)
# =========================

def create_tag_toppers_campaign(client, customer_id: str, mc_id: int, tracking_template: str, shopid: str, shopname: str, item_ids=None):
    base_shop = _clean_shopname(shopname)
    campaign_name = f"[shop:{base_shop}] [shop_id:{shopid}] [channel:directshopping] [label:tag_toppers]"
    budget_name = f"budget_{base_shop}_{shopid}_directshopping_tag_toppers_{int(time.time())}"
    # €5/dag
    budget_micros = 30_000_000

    # Gebruik MC-id uit bestaande campagne indien beschikbaar
    mc_id_effective = get_merchant_id_for_campaign(customer_id, shopid) or mc_id

    camp_res = add_standard_shopping_campaign(
        client=client,
        customer_id=customer_id,
        merchant_center_account_id=int(mc_id_effective),
        campaign_name=campaign_name,
        budget_name=budget_name,
        tracking_template=tracking_template,
        country="NL" if customer_id == customer_id_nl else ("BE" if customer_id == customer_id_be else "DE"),
        shopid=str(shopid),
        shopname=base_shop,
        label="tag_toppers",
        budget=budget_micros,
        final_url_suffix=None
    )
    if not camp_res:
        print(f"                ❌ Kon campagne niet aanmaken voor {base_shop} ({shopid})")
        return None

    # hergebruik of maak ad group
    ag_res = get_or_create_tag_toppers_adgroup(client, customer_id, camp_res, name="tag_toppers", bid_micros=200_000)
    ag_id = ag_res.split("/")[-1]

    # Boom plaatsen (ONLY specific item IDs)
    rebuild_tree_with_specific_item_ids(
        client, customer_id, int(ag_id),
        item_ids=item_ids,
        default_bid_micros=200_000
    )

    # Add shopping product ad with retry logic for concurrent modification errors
    max_retries = 3
    retry_delay = 2  # Start with 2 seconds

    for attempt in range(max_retries):
        try:
            time.sleep(retry_delay)  # Wait for product partition tree to stabilize
            add_shopping_product_ad_group_ad(client, customer_id, ag_res)
            print(f"                🆕 Campagne opgebouwd: {campaign_name}")
            break  # Success, exit retry loop
        except GoogleAdsException as ex:
            # Check if it's a concurrent modification error
            is_concurrent_error = any(
                (getattr(e.error_code, "database_error", None) and
                 str(e.error_code.database_error) == "CONCURRENT_MODIFICATION")
                for e in ex.failure.errors
            )

            if is_concurrent_error and attempt < max_retries - 1:
                retry_delay *= 2  # Exponential backoff
                print(f"                ⚠️ Concurrent modification detected, retrying in {retry_delay}s (attempt {attempt + 1}/{max_retries})...")
                continue
            else:
                # Either not a concurrent error, or we've exhausted retries
                print(f"                ❌ Failed to create ad after {attempt + 1} attempts")
                raise

    return camp_res

def get_branded(shop_name):
    if not shop_name:
        return 0

    sql = """
    WITH latest AS (
      SELECT shop_id, shop_name
      FROM beslistbi.bt.shop_list
      WHERE deleted_ind = 0
        AND shop_name = %s
      ORDER BY date DESC
      LIMIT 1
    )
    SELECT COALESCE(c.f_branded, 0) AS branded
    FROM latest l
    LEFT JOIN beslistbi.hda.efficy_shops s
      ON s.f_shop_id = l.shop_id
     AND s.actual_ind = 1
     AND s.deleted_ind = 0
    LEFT JOIN beslistbi.hda.efficy_shop_catman c
      ON c.k_shop = s.k_shop
     AND c.actual_ind = 1
     AND c.deleted_ind = 0
    LIMIT 1;
    """

    try:
        with closing(psycopg2.connect(
            dbname='beslistbi',
            user='j_vanschagen',
            password='asjWQ@dmasm(asdm23',
            host='production-redshiftstack-127n6djd-beslistredshift-zjsoh9hkk262.ccr4dsiux3yc.eu-central-1.redshift.amazonaws.com',
            port='5439'
        )) as conn, conn, closing(conn.cursor()) as cur:
            cur.execute(sql, (shop_name,))
            row = cur.fetchone()
            if row and row[0] is not None:
                # Sommige drivers geven bool terug; cast naar int
                return int(row[0])
            return 0
    except Exception as e:
        # Optioneel: loggen met print/logging
        # print(f"get_branded_for_shop error: {e}")
        return 0


def get_negatives(shopname):

    if "|" in shopname:
        shopname = shopname.split("|")[0]

    if ".nl" in shopname:
        domain = shopname.split(".nl")[0]
    elif ".com" in shopname:
        domain = shopname.split(".com")[0]
    elif ".be" in shopname:
        domain = shopname.split(".be")[0]
    elif ".de" in shopname:
        domain = shopname.split(".de")[0]

    else:
        return [shopname]
    return [shopname, domain]


def add_negative_keywords(client, customer_id, campaign_resource_name, negative_keywords):
    campaign_criterion_service = client.get_service("CampaignCriterionService")

    # Maak een lijst van operations om zowel EXACT als PHRASE varianten toe te voegen
    operations = []

    for keyword in negative_keywords:
        for match_type in [client.enums.KeywordMatchTypeEnum.EXACT, client.enums.KeywordMatchTypeEnum.PHRASE]:
            campaign_criterion_operation = client.get_type("CampaignCriterionOperation")
            campaign_criterion = campaign_criterion_operation.create

            campaign_criterion.campaign = campaign_resource_name
            campaign_criterion.negative = True  # Markeer als negatief zoekwoord
            campaign_criterion.keyword.text = keyword
            campaign_criterion.keyword.match_type = match_type  # Voeg zowel EXACT als PHRASE toe

            operations.append(campaign_criterion_operation)

    # Verstuur de mutatie-aanvraag naar Google Ads API
    try:
        response = campaign_criterion_service.mutate_campaign_criteria(
            customer_id=customer_id, operations=operations
        )
        print(
            f"                {len(negative_keywords) * 2} negatieve zoekwoorden toegevoegd (EXACT & PHRASE) aan campagne {campaign_resource_name}: {negative_keywords}")
    except GoogleAdsException as ex:
        print(f"                [Error] Fout bij toevoegen van negatieve zoekwoorden: {ex}")


# =========================
# Main
# =========================

# no_data
# [label_test] [shop:Wibra.nl] [shop_id:652337] [channel:directshopping] [label:no_data] [fallback]

if __name__ == "__main__":
    tag_rows = get_spreadsheet_input(return_json=False)
    print(f"nr of CPR-shops to process: {len(tag_rows)}")

    processed_rows = []  # Track successfully processed row numbers

    for campagne_data_cpr in tag_rows:
        shopname = campagne_data_cpr.get("shop_name", "")
        shopid = campagne_data_cpr.get("shop_id", "")
        domain = campagne_data_cpr.get("domain", "")
        item_ids = campagne_data_cpr.get("item_ids", [])
        row_number = campagne_data_cpr.get("row")  # Get row number for tracking

        if not shopid or not shopname or not domain:
            print(f"⚠️ Rij overgeslagen (ontbrekende velden): {campagne_data_cpr}")
            continue

        if domain == 'BE':
            customer_id = customer_id_be
            tracking_template = tracking_template_be
            mc_id = mc_id_be
        elif domain == 'NL':
            customer_id = customer_id_nl
            tracking_template = tracking_template_nl
            mc_id = mc_id_nl
        elif domain == 'DE':
            customer_id = customer_id_de
            tracking_template = tracking_template_de
            mc_id = mc_id_de
        else:
            print(f"⚠️ Onbekend domein: {domain}; rij overgeslagen.")
            continue

        row_processed_successfully = True  # Track if this row completed without critical errors

        # 1) Bestaande campagnes: boom vervangen door label+item IDs (OLD LOGIC - INVERSE)
        existing = find_campaigns_for_shop(client, customer_id, str(shopid), shopname)
        if existing:
            for camp_id, camp_name, camp_res in existing:
                print(f"                ➕ Label+Item ID boom in campagne: {camp_name} ({camp_id})")
                ad_groups = list_ad_groups_in_campaign(client, customer_id, camp_res)
                for ag_id, ag_res, ag_name in ad_groups:
                    try:
                        rebuild_tree_with_label_and_item_ids(
                            client, customer_id, int(ag_id),
                            ad_group_name=ag_name,
                            item_ids=item_ids,
                            default_bid_micros=200_000
                        )
                    except GoogleAdsException as ex:
                        print(f"                ❌ Fout in ad group {ag_id}: {ex.failure}")
                        row_processed_successfully = False
        else:
            print(f"                ℹ️ Geen bestaande campagnes gevonden voor shop_id {shopid} + shop {shopname}")

        # 2) Nieuwe (of hergebruik) tag_toppers campagne opzetten met ONLY specific item IDs (NEW LOGIC - INCLUSIVE)
        try:
            campaign_resource_name = create_tag_toppers_campaign(client, customer_id, mc_id, tracking_template, str(shopid), shopname, item_ids)
            branded = get_branded(shopname)

            if branded == 0:
                negative_keywords = get_negatives(shopname)
                add_negative_keywords(client, customer_id, campaign_resource_name, negative_keywords)

        except GoogleAdsException as ex:
            print(f"                ❌ Google Ads API error (create_tag_toppers): {ex.failure}")
            row_processed_successfully = False

        # Mark row as processed if completed successfully
        if row_processed_successfully and row_number:
            processed_rows.append(row_number)

    # Batch update all processed rows in the spreadsheet
    if processed_rows:
        print(f"\n📝 Updating spreadsheet: marking {len(processed_rows)} row(s) as processed...")
        print(f"   Rows: {processed_rows}")
        mark_rows_as_processed(processed_rows)
    else:
        print(f"\n⚠️ No rows were successfully processed, spreadsheet will not be updated")

    print("Klaar.")