import os
import pyotp
import requests
from dotenv import load_dotenv
from dhanhq import DhanContext, dhanhq

load_dotenv()

client_id = os.environ["DHAN_CLIENT_ID"]
pin = os.environ["DHAN_PIN"]
totp_secret = os.environ["DHAN_TOTP_SECRET"]


def generate_fresh_token():
    totp_code = pyotp.TOTP(totp_secret).now()
    response = requests.post(
        "https://auth.dhan.co/app/generateAccessToken",
        params={"dhanClientId": client_id, "pin": pin, "totp": totp_code},
    )
    response.raise_for_status()
    return response.json()["accessToken"]


# Generate a fresh token at startup and build the client with it
access_token = generate_fresh_token()
dhan_context = DhanContext(client_id, access_token)
dhan = dhanhq(dhan_context)