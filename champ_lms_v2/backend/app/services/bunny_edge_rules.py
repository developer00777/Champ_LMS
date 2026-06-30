"""
Bunny Edge Rules service — manages pull zone Edge Rules via Bunny API.
Replaces AWS WAF for:
  - VPN IP whitelist (block all IPs outside corporate CIDR)
  - Mobile User-Agent blocking (Android, iPhone, iPad)
  - Rate limiting note: Bunny handles this natively in pull zone settings

Edge Rules are configured on the CDN pull zone (not Stream).
Typically configured once at setup time via the setup script.
"""
import httpx
from app.core.config import get_settings

BUNNY_API_BASE = "https://api.bunny.net"


class BunnyEdgeRulesService:
    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def _headers(self) -> dict:
        return {
            "AccessKey": self.settings.bunny_account_api_key,
            "Content-Type": "application/json",
        }

    async def list_pull_zones(self) -> list[dict]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{BUNNY_API_BASE}/pullzone",
                headers=self._headers,
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()

    async def add_edge_rule(self, pull_zone_id: int, rule: dict) -> dict:
        """
        Add an Edge Rule to a pull zone.

        Example rule payloads:

        Block mobile User-Agents:
        {
            "Enabled": true,
            "Description": "Block mobile devices",
            "TriggerMatchingType": 1,   # 0=ALL, 1=ANY
            "Triggers": [
                {"Type": 3, "PatternMatches": ["*Android*","*iPhone*","*iPad*","*Mobile*"],
                 "PatternMatchingType": 0}   # Type 3 = RequestHeader, match User-Agent
            ],
            "ActionType": 2,   # 2 = BlockRequest
            "ActionParameter1": "403"
        }

        Block non-VPN IPs (allow only specific CIDR):
        {
            "Enabled": true,
            "Description": "VPN IP whitelist",
            "TriggerMatchingType": 0,   # ALL
            "Triggers": [
                {"Type": 1, "PatternMatches": ["!10.0.0.0/8"],
                 "PatternMatchingType": 0}   # Type 1 = VisitorIP
            ],
            "ActionType": 2,
            "ActionParameter1": "403"
        }
        """
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{BUNNY_API_BASE}/pullzone/{pull_zone_id}/edgerules/addOrUpdate",
                headers=self._headers,
                json=rule,
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()

    async def setup_security_rules(self, pull_zone_id: int, vpn_cidr: str) -> None:
        """
        Idempotent helper that sets up both security edge rules.
        Call once during infrastructure setup.
        """
        mobile_block_rule = {
            "Enabled": True,
            "Description": "Block mobile devices",
            "TriggerMatchingType": 1,
            "Triggers": [
                {
                    "Type": 3,
                    "PatternMatches": ["*Android*", "*iPhone*", "*iPad*", "*Mobile*", "*webOS*"],
                    "PatternMatchingType": 0,
                }
            ],
            "ActionType": 2,
            "ActionParameter1": "403",
        }

        vpn_whitelist_rule = {
            "Enabled": True,
            "Description": "VPN IP whitelist — block all non-VPN",
            "TriggerMatchingType": 0,
            "Triggers": [
                {
                    "Type": 1,
                    "PatternMatches": [f"!{vpn_cidr}"],
                    "PatternMatchingType": 0,
                }
            ],
            "ActionType": 2,
            "ActionParameter1": "403",
        }

        for rule in [mobile_block_rule, vpn_whitelist_rule]:
            await self.add_edge_rule(pull_zone_id, rule)


bunny_edge_rules = BunnyEdgeRulesService()
