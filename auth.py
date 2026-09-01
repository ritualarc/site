import os

import httpx
from authlib.integrations.starlette_client import OAuth

AUTH0_DOMAIN = os.environ.get("AUTH0_DOMAIN")
AUTH0_CLIENT_ID = os.environ.get("AUTH0_CLIENT_ID")
AUTH0_CLIENT_SECRET = os.environ.get("AUTH0_CLIENT_SECRET")

AUTH0_CONFIGURED = bool(AUTH0_DOMAIN and AUTH0_CLIENT_ID and AUTH0_CLIENT_SECRET)

oauth = OAuth()

if AUTH0_CONFIGURED:
    oauth.register(
        "auth0",
        client_id=AUTH0_CLIENT_ID,
        client_secret=AUTH0_CLIENT_SECRET,
        client_kwargs={"scope": "openid profile email"},
        server_metadata_url=f"https://{AUTH0_DOMAIN}/.well-known/openid-configuration",
    )

# Custom ID token claim (set by an Auth0 Action, see README) that carries the
# account type ("Member" or "Brand") chosen at signup, so a later Login can
# recover it without asking again.
ACCOUNT_TYPE_CLAIM = "https://ritualarc.app/account_type"

AUTH0_M2M_CLIENT_ID = os.environ.get("AUTH0_M2M_CLIENT_ID")
AUTH0_M2M_CLIENT_SECRET = os.environ.get("AUTH0_M2M_CLIENT_SECRET")

MANAGEMENT_API_CONFIGURED = bool(AUTH0_M2M_CLIENT_ID and AUTH0_M2M_CLIENT_SECRET and AUTH0_DOMAIN)


class ManagementAPIError(RuntimeError):
    pass


async def set_account_type(user_id: str, account_type: str) -> None:
    """Persist the chosen account type into the user's Auth0 app_metadata."""
    if not MANAGEMENT_API_CONFIGURED:
        raise ManagementAPIError(
            "AUTH0_M2M_CLIENT_ID and AUTH0_M2M_CLIENT_SECRET must be set to persist account type."
        )

    async with httpx.AsyncClient(timeout=10) as client:
        token_response = await client.post(
            f"https://{AUTH0_DOMAIN}/oauth/token",
            json={
                "grant_type": "client_credentials",
                "client_id": AUTH0_M2M_CLIENT_ID,
                "client_secret": AUTH0_M2M_CLIENT_SECRET,
                "audience": f"https://{AUTH0_DOMAIN}/api/v2/",
            },
        )
        token_response.raise_for_status()
        access_token = token_response.json()["access_token"]

        update_response = await client.patch(
            f"https://{AUTH0_DOMAIN}/api/v2/users/{user_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"app_metadata": {"account_type": account_type}},
        )
        update_response.raise_for_status()
