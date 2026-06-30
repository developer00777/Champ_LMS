"""
Bunny DNS service — programmatic DNS zone management.
Replaces Route 53.

Used during initial setup to create/update A records for:
  - learn.championsgroup.com  → VPS IP
  - api.championsgroup.com    → VPS IP
  - cdn.championsgroup.com    → (CNAME to Bunny CDN pull zone hostname)
"""
import httpx
from app.core.config import get_settings

BUNNY_DNS_BASE = "https://api.bunny.net"


class BunnyDNSService:
    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def _headers(self) -> dict:
        return {
            "AccessKey": self.settings.bunny_account_api_key,
            "Content-Type": "application/json",
        }

    async def list_zones(self) -> list[dict]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{BUNNY_DNS_BASE}/dnszone",
                headers=self._headers,
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json().get("Items", [])

    async def create_zone(self, domain: str) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{BUNNY_DNS_BASE}/dnszone",
                headers=self._headers,
                json={"Domain": domain},
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()

    async def add_record(
        self,
        zone_id: int,
        record_type: str,
        name: str,
        value: str,
        ttl: int = 300,
    ) -> dict:
        """
        record_type: 'A' | 'CNAME' | 'TXT' | 'MX'
        name: subdomain (empty string for apex)
        value: IP address or target hostname
        """
        # Bunny DNS record type IDs: 0=A, 1=AAAA, 2=CNAME, 3=TXT, 4=MX, 5=Redirect, 6=Flatten
        type_map = {"A": 0, "AAAA": 1, "CNAME": 2, "TXT": 3, "MX": 4}
        async with httpx.AsyncClient() as client:
            resp = await client.put(
                f"{BUNNY_DNS_BASE}/dnszone/{zone_id}/records",
                headers=self._headers,
                json={
                    "Type": type_map.get(record_type.upper(), 0),
                    "Name": name,
                    "Value": value,
                    "Ttl": ttl,
                },
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()

    async def delete_record(self, zone_id: int, record_id: int) -> None:
        async with httpx.AsyncClient() as client:
            resp = await client.delete(
                f"{BUNNY_DNS_BASE}/dnszone/{zone_id}/records/{record_id}",
                headers=self._headers,
                timeout=30,
            )
            resp.raise_for_status()


bunny_dns = BunnyDNSService()
