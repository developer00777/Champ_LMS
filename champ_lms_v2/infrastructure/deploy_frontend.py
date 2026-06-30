#!/usr/bin/env python3
"""
Deploy SvelteKit static build to Bunny Storage (frontend zone).
Run: python infrastructure/deploy_frontend.py
"""
import asyncio
import mimetypes
import os
from pathlib import Path
import httpx
from dotenv import load_dotenv

load_dotenv()

STORAGE_HOST = os.environ.get("BUNNY_STORAGE_HOST", "storage.bunnycdn.com")
ZONE = os.environ["BUNNY_STORAGE_FRONTEND_ZONE"]
PASSWORD = os.environ["BUNNY_STORAGE_FRONTEND_PASSWORD"]
BUILD_DIR = Path(__file__).parent.parent / "frontend" / "build"


async def upload_file(client: httpx.AsyncClient, rel_path: str, abs_path: Path) -> None:
    data = abs_path.read_bytes()
    ct = mimetypes.guess_type(str(abs_path))[0] or "application/octet-stream"
    url = f"https://{STORAGE_HOST}/{ZONE}/{rel_path}"
    resp = await client.put(
        url,
        content=data,
        headers={"AccessKey": PASSWORD, "Content-Type": ct},
        timeout=60,
    )
    symbol = "✓" if resp.status_code == 201 else "✗"
    print(f"  {symbol} {rel_path} ({len(data) // 1024}KB)")


async def main() -> None:
    if not BUILD_DIR.exists():
        print(f"Build directory not found: {BUILD_DIR}")
        print("Run: cd frontend && npm run build")
        return

    files = list(BUILD_DIR.rglob("*"))
    files = [f for f in files if f.is_file()]
    print(f"Deploying {len(files)} files to Bunny Storage zone '{ZONE}'...\n")

    async with httpx.AsyncClient() as client:
        for f in files:
            rel = str(f.relative_to(BUILD_DIR))
            await upload_file(client, rel, f)

    print(f"\n✓ Deployed to https://{STORAGE_HOST}/{ZONE}/")
    print("Don't forget to invalidate Bunny CDN cache if needed.")


if __name__ == "__main__":
    asyncio.run(main())
