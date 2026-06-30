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
BUNNY_STREAM_BASE = "https://video.bunnycdn.com"

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
    """
    Bunny Edge Rules trigger types:
      Type 0 = URL path
      Type 1 = RequestHeader (pattern matches header value)
      Type 3 = UrlExtension
      Type 4 = CountryCode
      Type 5 = RemoteIP  ← correct type for IP matching

    NOTE: Bunny Edge Rules don't support CIDR negation ("block all IPs NOT in range")
    in a single rule. VPN IP whitelisting is handled at the Caddy layer on the VPS
    (see infrastructure/Caddyfile — simpler, more reliable, no CDN bypass risk).

    This function sets up the mobile UA block only.
    """
    mobile_block = {
        "Enabled": True,
        "Description": "Block mobile devices",
        "TriggerMatchingType": 1,  # ANY trigger matches
        "Triggers": [{
            "Type": 1,  # RequestHeader
            "PatternMatches": ["*Android*", "*iPhone*", "*iPad*", "*Mobile*", "*webOS*"],
            "PatternMatchingType": 0,  # 0 = MatchAny
        }],
        "ActionType": 2,  # BlockRequest
        "ActionParameter1": "403",
    }
    resp = await client.post(
        f"{BUNNY_API}/pullzone/{pull_zone_id}/edgerules/addOrUpdate",
        headers=HEADERS,
        json=mobile_block,
    )
    status = "✓" if resp.status_code in (200, 201) else "✗"
    print(f"  {status} Edge rule 'Block mobile devices': {resp.status_code}")
    print("  ↩ VPN IP whitelist: handled at Caddy layer (see Caddyfile) — Bunny Edge Rules")
    print("    don't support CIDR negation. Add 'remote_ip' directive in Caddyfile.")


async def verify_stream_library(client: httpx.AsyncClient, library_id: str) -> dict:
    """
    Verify an existing Bunny Stream library (created manually in dashboard).
    Bunny Stream library creation via API requires the account-level management API
    which uses a different base URL. Since the library already exists from manual
    setup (ID: 694284), we just verify and return its details.
    """
    if not STREAM_API_KEY:
        print("  ↩ BUNNY_STREAM_API_KEY not set — skip stream library check")
        return {}
    if not library_id:
        print("  ↩ No BUNNY_STREAM_LIBRARY_ID — skip (library already created manually)")
        return {}

    headers = {"AccessKey": STREAM_API_KEY, "Content-Type": "application/json"}
    resp = await client.get(
        f"{BUNNY_STREAM_BASE}/library/{library_id}",
        headers=headers,
        timeout=15,
    )
    if resp.status_code == 200:
        data = resp.json()
        print(f"  ✓ Stream library verified — videos: {data.get('videoCount', 0)}, collections: {data.get('collectionCount', 0)}")
        return data
    else:
        print(f"  ✗ Stream library check failed: {resp.status_code} {resp.text}")
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

        print("\n4. Bunny Stream library (verify existing)")
        stream_library_id = os.environ.get("BUNNY_STREAM_LIBRARY_ID", "")
        stream_lib = await verify_stream_library(client, stream_library_id)

        print("\n5. Bunny DNS")
        await create_dns_zone(client, DOMAIN, VPS_IP)

    print("\n=== Setup complete ===")
    print("\n── Values to copy into backend/.env ──")
    print(f"  BUNNY_STREAM_LIBRARY_ID={stream_library_id}")
    print(f"  BUNNY_STREAM_CDN_HOSTNAME=vz-727d9382-c9a.b-cdn.net  # from Bunny Stream dashboard")
    print(f"  BUNNY_STREAM_TOKEN_SECRET={os.environ.get('BUNNY_STREAM_TOKEN_SECRET','')}")
    print(f"  BUNNY_STREAM_WEBHOOK_SECRET={os.environ.get('BUNNY_STREAM_API_KEY','')}  # = Stream API key")
    print()
    print("── Manual steps remaining ──")
    print("  1. Bunny dashboard → Pull Zones → champ-lms-cdn → Hostnames")
    print(f"     Add: cdn.learn.{DOMAIN}")
    print("  2. Pull Zones → champ-lms-cdn → Optimizer → Enable Image Optimization")
    print("  3. Add VPN IP whitelist in Caddyfile (see infrastructure/Caddyfile)")
    print(f"  4. Change nameservers at your registrar to Bunny DNS (check dashboard → DNS → {DOMAIN})")


if __name__ == "__main__":
    asyncio.run(main())
