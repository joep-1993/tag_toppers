# PROJECT INDEX
_Project structure and technical specs. Update when: creating files, adding dependencies, defining schemas._

## Stack
Python 3.x
Google Ads API
Google Sheets API
FastAPI (if applicable)

## Directory Structure
```
tag_toppers/
  cc1/             → CC1 documentation system
  creds/           → Credentials (gitignored)
  script/          → Scripts directory
  .claude/         → Claude Code settings
  .env             → Environment variables
  .gitignore       → Git ignore rules
  README.md        → Project overview
  CLAUDE.md        → Claude Code instructions
```

## Environment Variables
_Document all required and optional environment variables_

### Required
```bash
GOOGLE_CLIENT_ID="your-google-client-id"
GOOGLE_CLIENT_SECRET="your-google-client-secret"
# Add other required variables as discovered
```

### Optional
```bash
# Add optional variables with defaults
```

## Database Schema
_Define tables, fields, types, and relationships when created_

### Tables
```sql
-- Add CREATE TABLE statements or ORM model definitions as needed
```

### Indexes
_Document database indexes for performance_

### Migrations
_Track migration history if applicable_

## API Endpoints
_Document as built_

## Core Files
_Track important files and their purposes_

### Configuration
- `.env` - Environment variables
- `creds/` - Google API credentials (gitignored)
- `.gitignore` - Excludes sensitive files (creds, *.json, credentials)
- `CLAUDE.md` - Claude Code instructions with project setup and commands

### Main Components
_Add as you build_

- `GSD_tagtoppers.py` - Main script for Google Shopping campaigns with exclusive Item-ID logic
- `listing_tree.py` - Listing tree rebuild logic with custom label exclusion preservation - detects and preserves existing negative custom label units while adding item ID exclusions
- `listing_tree_readme.md` - Documentation for listing tree rebuild logic

### Test Files
- `test_fixed_script.py` - Test script for verifying custom label exclusion preservation
- `test_exclusion_preservation.py` - Alternative test script for tree rebuild validation

## Dependencies
_Major libraries and frameworks_

- google-ads
- google-api-python-client
- google-auth-httplib2
- google-auth-oauthlib

## Key Decisions
_Important technical and architectural decisions_

- Credentials are stored in `creds/` folder and excluded from git
- All JSON files are gitignored for security
- Using Google OAuth for authentication

---
_Last updated: 2025-10-29_
