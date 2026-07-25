"""Constants for the Candy Simply-Fi (Cloud) integration."""

DOMAIN = "candy_simplyfi"

# Config entry keys
CONF_API_ENDPOINT = "api_endpoint"
CONF_AUTH_ENDPOINT = "auth_endpoint"
CONF_CLIENT_ID = "client_id"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_APPLIANCE_ID = "appliance_id"
CONF_APPLIANCE_NAME = "appliance_name"

# Fixed values — identical for every Simply-Fi user. The client_id is the
# Salesforce "connected app" embedded in the official Candy Android app, and the
# auth/api hosts are Candy's own. Only the per-user refresh_token differs, so the
# config flow asks for that alone. These stay overridable via the entry data.
DEFAULT_AUTH_ENDPOINT = "https://account.candy-home.com/CandyApp"
DEFAULT_API_ENDPOINT = "https://simply-fi.herokuapp.com"
DEFAULT_CLIENT_ID = (
    "3MVG9QDx8IX8nP5T2Ha8ofvlmjKuido4mcuSVCv4GwStG0Lf84ccYQylvDYy9d_"
    "ZLtnyAPzJt4khJoNYn_QVB"
)

# OAuth redirect the app uses; the tokens arrive in this URL's fragment.
OAUTH_REDIRECT_URI = "candy://mobilesdk/detect/oauth/done"

# Browser login URL (the "easy" way to get a refresh_token without an emulator):
# open it, log in, and read refresh_token from the candy:// redirect fragment.
AUTHORIZE_URL = (
    DEFAULT_AUTH_ENDPOINT
    + "/services/oauth2/authorize/expid_mobileCandy"
    + "?display=touch&response_type=hybrid_token"
    + f"&client_id={DEFAULT_CLIENT_ID}"
    + "&scope=api%20id%20openid%20refresh_token%20web"
    + f"&redirect_uri={OAUTH_REDIRECT_URI}"
    + "&device_id=homeassistant"
)

DEFAULT_SCAN_INTERVAL = 300  # seconds (NFC stats change rarely; 5 min is plenty)

# Headers that mimic the official Simply-Fi Android app.
APP_HEADERS = {
    "Salesforce-Auth": "1",
    "Device-Language": "en",
    "Device-Model": "HomeAssistant",
    "Device-Os": "Android 13",
    "App-Version-Name": "3.7.1",
    "App-Version-Code": "211",
    "Player-Id": "00000000-0000-0000-0000-000000000000",
}

USER_AGENT = (
    "SalesforceMobileSDK/10.2.0 android mobile/13 (HomeAssistant) "
    "simply-Fi/3.7.1(211) Native"
)

# Mapping of the raw current_status_parameters keys.
# Machine mode (MachMd)
MACHINE_STATE = {
    1: "Idle",
    2: "Running",
    3: "Paused",
    4: "Delayed start selection",
    5: "Delayed start programmed",
    6: "Error",
    7: "Finished",
    8: "Finished",
}

# Program phase (PrPh)
PROGRAM_STATE = {
    0: "Stopped",
    1: "Pre-wash",
    2: "Wash",
    3: "Rinse",
    4: "Last rinse",
    5: "End",
    6: "Drying",
    7: "Error",
    8: "Steam",
    9: "Spin - Good Night",
    10: "Spin",
}
