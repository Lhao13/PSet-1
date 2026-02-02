import requests
from mage_ai.data_preparation.shared.secrets import get_secret_value

@custom
def execute(**kwargs):
    url = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"

    auth = (
        get_secret_value("QBO_CLIENT_ID"),
        get_secret_value("QBO_CLIENT_SECRET")
    )

    data = {
        "grant_type": "refresh_token",
        "refresh_token": get_secret_value("QBO_REFRESH_TOKEN")
    }

    response = requests.post(url, data=data, auth=auth)
    response.raise_for_status()

    access_token = response.json()["access_token"]

    print("access token obtenida")

    return access_token