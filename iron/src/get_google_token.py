"""
get_google_token.py
───────────────────
Run this script LOCALLY on your own computer (not on PebbleHost) to
authorise Iron Bot with your Google account and generate token.json.

Steps:
  1. Make sure credentials.json is in the same folder as this script
  2. Run:  python get_google_token.py
  3. A browser window will open – sign in and click Allow
  4. token.json will be created in this folder
  5. Upload token.json to your PebbleHost server at iron/src/token.json

Requirements (install locally):  pip install google-auth-oauthlib
"""

import json
import sys
import os

SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']


def main():
    creds_file = os.path.join(os.path.dirname(__file__), 'credentials.json')
    token_file = os.path.join(os.path.dirname(__file__), 'token.json')

    if not os.path.exists(creds_file):
        print('ERROR: credentials.json not found.')
        print('Download it from Google Cloud Console → APIs & Services → Credentials.')
        sys.exit(1)

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print('ERROR: google-auth-oauthlib is not installed.')
        print('Run:  pip install google-auth-oauthlib')
        sys.exit(1)

    print('Opening your browser to authorise Iron Bot with Google Calendar...')
    print('(If the browser does not open, check the URL printed below.)\n')

    flow = InstalledAppFlow.from_client_secrets_file(creds_file, SCOPES)
    creds = flow.run_local_server(port=0, prompt='consent')

    token_data = {
        'token':         creds.token,
        'refresh_token': creds.refresh_token,
        'client_id':     creds.client_id,
        'client_secret': creds.client_secret,
    }

    with open(token_file, 'w') as f:
        json.dump(token_data, f, indent=2)

    print(f'\nSuccess! token.json saved to:\n  {token_file}')
    print('\nNEXT STEP:')
    print('  Upload token.json to your PebbleHost server at:')
    print('  iron/src/token.json')
    print('\nThen run  !calendar status  in Discord to confirm.')


if __name__ == '__main__':
    main()
