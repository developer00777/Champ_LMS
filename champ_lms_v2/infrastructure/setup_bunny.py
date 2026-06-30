#!/usr/bin/env python3
"""
Bunny CDN setup script — run once to configure all Bunny services.

Usage:
    pip install httpx python-dotenv
    python setup_bunny.py

Required env vars (set in .env or environment):
    BUNNY_ACCOUNT_API_KEY
    VPN_CIDR  (e.g. 10.0.0.0/8)
    VPS_IP    (your server's public IP)
    DOMAIN    (e.g. championsgroup.com)
"""
import asyncio
import os
import sys
from dotenv import load_dotenv
import httpx

load_dotenv()

BUNNY_API = "https://api.bunny.net"
BUNNY_STREAM_API = "https://video.bunnycdn.com"

API_KEY = os.environ["BUNNY_ACCOUNT_API_KEY"]
VPN_CIDR = os.environ.get("VPN_CIDR", "10.0.0.0/8")
VPS_IP = os.environ["VPS_IP"]
DOMAIN = os.environ.get("DOMAIN", "championsgroup.com")
STREAM_API_KEY = os.environ.get("BUNNY_STREAM_API_KEY", "")

HEADERS = {"AccessKey": API_KEY, "Content-Type": "application/json"}


async def create_storage_zone(client: httpx.AsyncClient, name: str, region: str = "DE") -> dict:
    resp = await client.post(
        f"{BUNNY_API}/storagezone",
        headers=HEADERS,
        json={"Name": name, "Region": region, "ZoneTier": 0},
    )
    if resp.status_code == 201:
        data = resp.json()
        print(f"  ✓ Storage zone '{name}' created — Password: {data.get('Password')}")
        return data
    elif resp.status_code == 400 and "already exists" in resp.text.lower():
        print(f"  ↩ Storage zone '{name}' already exists")
        # Fetch existing
        list_resp = await client.get(f"{BUNNY_API}/storagezone", headers=HEADERS)
        zones = list_resp.json().get("Items", [])
        for z in zones:
            if z["Name"] == name:
                return z
    else:
        print(f"  ✗ Failed to create '{name}': {resp.status_code} {resp.text}")
    return {}


async def create_pull_zone(
    client: httpx.AsyncClient,
    name: str,
    origin_url: str,
    add_cdn_hostname: str | None = None,
) -> dict:
    resp = await client.post(
        f"{BUNNY_API}/pullzone",
        headers=HEADERS,
        json={
            "Name": name,
            "OriginUrl": origin_url,
            "Type": 0,
            "EnableGeoZoneUS": True,
            "EnableGeoZoneEU": True,
            "EnableGeoZoneASIA": True,
        },
    )
    if resp.status_code in (200, 201):
        data = resp.json()
        print(f"  ✓ Pull zone '{name}' created — hostname: {data.get('Hostnames', [{}])[0].get('Value')}")
        return data
    else:
        print(f"  ✗ Pull zone '{name}': {resp.status_code} {resp.text}")
    return {}


async def add_edge_rules(client: httpx.AsyncClient, pull_zone_id: int, vpn_cidr: str) -> None:
    rules = [
        {
            "Enabled": True,
            "Description": "Block mobile devices",
            "TriggerMatchingType": 1,
            "Triggers": [{
                "Type": 3,
                "PatternMatches": ["*Android*", "*iPhone*", "*iPad*", "*Mobile*", "*webOS*"],
                "PatternMatchingType": 0,
            }],
            "ActionType": 2,
            "ActionParameter1": "403",
        },
        {
            "Enabled": True,
            "Description": "VPN IP whitelist",
            "TriggerMatchingType": 0,
            "Triggers": [{
                "Type": 1,
                "PatternMatches": [f"!{vpn_cidr}"],
                "PatternMatchingType": 0,
            }],
            "ActionType": 2,
            "ActionParameter1": "403",
        },
    ]
    for rule in rules:
        resp = await client.post(
            f"{BUNNY_API}/pullzone/{pull_zone_id}/edgerules/addOrUpdate",
            headers=HEADERS,
            json=rule,
        )
        status = "✓" if resp.status_code in (200, 201) else "✗"
        print(f"  {status} Edge rule '{rule['Description']}': {resp.status_code}")


async def create_stream_library(client: httpx.AsyncClient, name: str) -> dict:
    if not STREAM_API_KEY:
        print("  ↩ BUNNY_STREAM_API_KEY not set — skip stream library creation")
        return {}
    headers = {"AccessKey": STREAM_API_KEY, "Content-Type": "application/json"}
    resp = await client.post(
        f"{BUNNY_STREAM_API}/library",
        headers=headers,
        json={
            "Name": name,
            "ReplicationRegions": ["DE", "NY", "SG"],
            "EnableTokenAuthentication": True,
            "TokenAuthenticationKey": os.environ.get("BUNNY_STREAM_TOKEN_SECRET", ""),
        },
    )
    if resp.status_code in (200, 201):
        data = resp.json()
        print(f"  ✓ Stream library '{name}' — ID: {data.get('Id')}, CDN: {data.get('PullZone')}")
        return data
    else:
        print(f"  ✗ Stream library: {resp.status_code} {resp.text}")
    return {}


async def create_dns_zone(client: httpx.AsyncClient, domain: str, vps_ip: str) -> None:
    resp = await client.post(
        f"{BUNNY_API}/dnszone",
        headers=HEADERS,
        json={"Domain": domain},
    )
    if resp.status_code in (200, 201):
        zone_id = resp.json().get("Id")
        print(f"  ✓ DNS zone '{domain}' created — ID: {zone_id}")

        # Type map: 0=A, 2=CNAME
        records = [
            (0, "learn", vps_ip),     # learn.domain → VPS
            (0, "api", vps_ip),       # api.domain → VPS
        ]
        for rtype, name, value in records:
            r = await client.put(
                f"{BUNNY_API}/dnszone/{zone_id}/records",
                headers=HEADERS,
                json={"Type": rtype, "Name": name, "Value": value, "Ttl": 300},
            )
            symbol = "✓" if r.status_code in (200, 201) else "✗"
            print(f"  {symbol} DNS record {name}.{domain} → {value}")
    else:
        print(f"  ↩ DNS zone: {resp.status_code} {resp.text}")


async def main() -> None:
    print("\n=== Champ LMS v2 — Bunny Setup ===\n")

    async with httpx.AsyncClient(timeout=30) as client:

        print("1. Storage zones")
        thumbs_zone = await create_storage_zone(client, "champ-lms-thumbs")
        frontend_zone = await create_storage_zone(client, "champ-lms-frontend")

        print("\n2. CDN Pull zone (thumbnails + frontend)")
        if thumbs_zone.get("Id"):
            origin = f"https://storage.bunnycdn.com/{thumbs_zone['Name']}/"
            pull_zone = await create_pull_zone(client, "champ-lms-cdn", origin)

            if pull_zone.get("Id"):
                print("\n3. Edge Rules")
                await add_edge_rules(client, pull_zone["Id"], VPN_CIDR)

        print("\n4. Bunny Stream library")
        stream_lib = await create_stream_library(client, "champ-lms-stream")

        print("\n5. Bunny DNS")
        await create_dns_zone(client, DOMAIN, VPS_IP)

    print("\n=== Setup complete ===")
    print("\nNext steps:")
    print("  1. Copy the storage zone passwords to .env")
    print("  2. Set BUNNY_STREAM_LIBRARY_ID and BUNNY_STREAM_CDN_HOSTNAME in .env")
    print("  3. Add custom hostname 'cdn.learn.{DOMAIN}' to the pull zone in Bunny dashboard")
    print("  4. Enable Bunny Optimizer on the pull zone for WebP/resize support")
    print("  5. Configure Bunny Stream webhook URL: https://api.{DOMAIN}/webhooks/bunny-stream")
    print("  6. Point your domain's nameservers to Bunny DNS (shown in dashboard)")


if __name__ == "__main__":
    asyncio.run(main())
