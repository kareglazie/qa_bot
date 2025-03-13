import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
TG_ID_DEVELOPER = os.getenv("ADMIN_ID_DEVELOPER", "")
# TG_ID_MASTER = os.getenv("ADMIN_ID_MASTER", "")
