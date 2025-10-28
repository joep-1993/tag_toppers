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

#### Spreadsheet Updates
- **Service Account Permissions**: Need `https://www.googleapis.com/auth/spreadsheets` scope (not readonly)
- **Batch Updates**: Use `batchUpdate` API for efficient multi-row updates
- **Column G Pattern**: Track processed status in column G, only update rows that completed successfully
- **Error Handling**: Always include detailed error messages and traceback for Google Sheets API failures
