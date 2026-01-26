import os
from dotenv import load_dotenv
from telethon.sync import TelegramClient
from telethon.sessions import StringSession

load_dotenv(".env")

api_id = int(os.environ["TG_API_ID"])
api_hash = os.environ["TG_API_HASH"]

with TelegramClient(StringSession(), api_id, api_hash) as client:
    # При первом запуске спросит телефон/код/2FA
    print("TG_SESSION=" + client.session.save())
