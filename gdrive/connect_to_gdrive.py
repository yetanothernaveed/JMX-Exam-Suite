import gspread
from google.oauth2.service_account import Credentials

# Define the scope
scopes = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# Authenticate
creds = Credentials.from_service_account_file("/home/naveed/Projects/CSE221/testbench/service_account.json", scopes=scopes)
CLIENT = gspread.authorize(creds)

if __name__ == "__main__":
    print("Connected to Google Drive successfully!")
    print("Client object:", CLIENT)
