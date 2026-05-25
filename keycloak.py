from __future__ import annotations

from typing import Any

import requests

from api import normalize_base_url, paginated_get, request_json, resolve_secret


def keycloak_session(
    keycloak_base_url: str,
    auth_realm: str,
    client_id: str,
    client_secret: str,
) -> requests.Session:
    session = requests.Session()
    token_url = f"{normalize_base_url(keycloak_base_url)}/realms/{auth_realm}/protocol/openid-connect/token"
    token = request_json(
        session,
        "POST",
        token_url,
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": resolve_secret(client_secret),
        },
    )
    access_token = token.get("access_token")
    if not access_token:
        raise RuntimeError("Keycloak token response did not include access_token")

    session.headers.update({"Authorization": f"Bearer {access_token}"})
    return session


def user_federated_identity(
    session: requests.Session,
    keycloak_base_url: str,
    realm: str,
    user_id: str,
    linked_provider: str,
) -> dict[str, Any] | None:
    url = f"{normalize_base_url(keycloak_base_url)}/admin/realms/{realm}/users/{user_id}/federated-identity"
    identities = request_json(session, "GET", url)
    for identity in identities:
        if identity.get("identityProvider") == linked_provider:
            return identity
    return None


def user_matches_group(
    session: requests.Session,
    keycloak_base_url: str,
    realm: str,
    user_id: str,
    group: str,
) -> bool:
    url = f"{normalize_base_url(keycloak_base_url)}/admin/realms/{realm}/users/{user_id}/groups"
    groups = request_json(session, "GET", url)
    return any(item.get("name") == group or item.get("path") == group for item in groups)


def user_matches_realm_role(
    session: requests.Session,
    keycloak_base_url: str,
    realm: str,
    user_id: str,
    realm_role: str,
) -> bool:
    url = f"{normalize_base_url(keycloak_base_url)}/admin/realms/{realm}/users/{user_id}/role-mappings/realm/composite"
    roles = request_json(session, "GET", url)
    return any(role.get("name") == realm_role for role in roles)


def list_keycloak_users(
    *,
    keycloak_base_url: str,
    realm: str,
    auth_realm: str,
    client_id: str,
    client_secret: str,
    linked_provider: str | None,
    group: str | None,
    realm_role: str | None,
    page_size: int,
) -> list[dict[str, Any]]:
    session = keycloak_session(keycloak_base_url, auth_realm, client_id, client_secret)
    users_url = f"{normalize_base_url(keycloak_base_url)}/admin/realms/{realm}/users"
    users = paginated_get(session, users_url, page_size=page_size, pagination="first")

    results: list[dict[str, Any]] = []
    for user in users:
        user_id = user["id"]
        identity = None

        if linked_provider:
            identity = user_federated_identity(session, keycloak_base_url, realm, user_id, linked_provider)
            if identity is None:
                continue

        if group and not user_matches_group(session, keycloak_base_url, realm, user_id, group):
            continue

        if realm_role and not user_matches_realm_role(session, keycloak_base_url, realm, user_id, realm_role):
            continue

        results.append(
            {
                "userId": user_id,
                "username": user.get("username"),
                "email": user.get("email"),
                "enabled": user.get("enabled"),
                "federatedUserID": identity.get("userId") if identity else None,
                "federatedUsername": identity.get("userName") if identity else None,
            }
        )

    return results
