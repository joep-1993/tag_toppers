# CLAUDE.md

@~/.claude/cc1-global.md

## Project-Specific Configuration
_Add your project-specific details below_

### Project Overview
Tag Toppers is a Google Ads campaign management tool that automates campaign creation and management using the Google Ads API and Google Sheets integration.

### Development Setup
1. Ensure Python 3.x is installed
2. Install required dependencies:
   ```bash
   pip3 install --quiet google-ads google-api-python-client google-auth-httplib2 google-auth-oauthlib
   ```
3. Set up Google OAuth credentials:
   ```bash
   export GOOGLE_CLIENT_ID="your-google-client-id"
   export GOOGLE_CLIENT_SECRET="your-google-client-secret"
   ```
4. Place Google API credentials in `creds/` directory (gitignored)

### Key Commands
```bash
# Run Python scripts
python3 script_name.py

# Install dependencies
pip3 install --quiet google-ads google-api-python-client google-auth-httplib2 google-auth-oauthlib
```

### Important Notes
- All credentials are stored in `creds/` directory and excluded from git
- JSON files are gitignored for security
- Environment variables for Google OAuth are configured in shell

---
_CC1 System initialized: 2025-10-17_
