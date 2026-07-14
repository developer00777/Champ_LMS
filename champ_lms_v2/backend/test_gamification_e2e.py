"""
Comprehensive E2E test for Champ LMS v2 gamification, learning paths,
collaborative challenges, and social features.

Prerequisites:
- Backend running: cd backend && source .venv/bin/activate && uvicorn app.main:app --reload
- MongoDB + Redis reachable
- Sample data seeded: python seed_demo.py

Run:
    source .venv/bin/activate
    python test_gamification_e2e.py
"""
import asyncio
import sys
import httpx

BASE = "http://127.0.0.1:8000"

USER = {
    "email": "e2e.test@champ.local",
    "full_name": "E2E Tester",
    "password": "learner123",
    "department": "sales",
}

USER2 = {
    "email": "e2e.test2@champ.local",
    "full_name": "E2E Teammate",
    "password": "learner123",
    "department": "sales",
}


def ok(resp: httpx.Response, label: str) -> dict:
    if resp.status_code >= 400:
        print(f"FAIL  {label}: {resp.status_code} {resp.text[:200]}")
        sys.exit(1)
    return resp.json()


async def main() -> None:
    async with httpx.AsyncClient(base_url=BASE, timeout=30) as client:
        print("=" * 60)
        print("Champ LMS v2 — Full E2E Test")
        print("=" * 60)

        # 1. Register + login two users
        for u in [USER, USER2]:
            await client.post("/auth/register", json=u)
        token1 = ok(await client.post("/auth/token", data={"username": USER["email"], "password": USER["password"]}, headers={"Content-Type": "application/x-www-form-urlencoded"}), "login1")["access_token"]
        token2 = ok(await client.post("/auth/token", data={"username": USER2["email"], "password": USER2["password"]}, headers={"Content-Type": "application/x-www-form-urlencoded"}), "login2")["access_token"]
        h1 = {"Authorization": f"Bearer {token1}"}
        h2 = {"Authorization": f"Bearer {token2}"}
        print(f"\n[1] Auth: 2 users logged in ({USER['department']})")

        # 2. Find modules + complete episodes
        modules = ok(await client.get("/modules", headers=h1), "list modules")
        target = next((m for m in modules if m.get("category") == "sales"), modules[0] if modules else None)
        assert target, "No sales module found"
        detail = ok(await client.get(f"/modules/{target['id']}", headers=h1), "module detail")
        for ep in detail["episodes"]:
            total = ep.get("duration_seconds") or 300
            resp = await client.post("/progress", json={"episode_id": ep["id"], "watched_seconds": total, "total_seconds": total}, headers=h1)
            ok(resp, f"progress {ep['title']}")
            r = resp.json()
            if r.get("rewards"):
                rw = r["rewards"]
                if rw.get("module_completion"):
                    print(f"  Module completed! pts={rw['module_completion']['points']} xp={rw['module_completion']['xp']}")
                if rw.get("first_to_complete"):
                    print(f"  First to complete! +{rw['first_to_complete']['points']} pts")
        print("[2] Progress: all episodes completed for sales module")

        # 3. Check gamification state
        me = ok(await client.get("/auth/me", headers=h1), "me")
        print(f"[3] User state: points={me['points']} xp={me['xp']} level={me['level']}")

        level_info = ok(await client.get("/me/level", headers=h1), "level")
        print(f"    Level: {level_info['tier']} (lvl {level_info['level']}) XP to next: {level_info['xp_to_next_level']}")

        xp_hist = ok(await client.get("/me/xp-history?limit=5", headers=h1), "xp history")
        print(f"    XP events: {len(xp_hist)}")

        quests = ok(await client.get("/quests/me", headers=h1), "quests")
        print(f"    Quests: {len(quests)} active")
        for q in quests:
            status = "DONE" if q["completed"] else f"{q['progress']}/{q['target']}"
            print(f"      [{q['scope']}] {q['title']}: {status}")

        badges = ok(await client.get("/badges/me", headers=h1), "badges")
        print(f"    Badges: {len(badges)} earned")

        lb = ok(await client.get(f"/leaderboard?department={USER['department']}&limit=3", headers=h1), "leaderboard")
        print(f"    Dept leaderboard: {len(lb)} entries")

        # 4. Learning Paths
        paths = ok(await client.get(f"/paths?department={USER['department']}", headers=h1), "list paths")
        print(f"\n[4] Learning Paths: {len(paths)} found for {USER['department']}")
        for p in paths:
            print(f"  {p['variant']} {p['title']} ({p['total_nodes']} nodes)")

        if paths:
            path_detail = ok(await client.get(f"/paths/{paths[0]['id']}", headers=h1), "path detail")
            print(f"  Opened: {path_detail['title']}")
            print(f"  Current node: {path_detail['current_node']}")
            print(f"  Mastered: {path_detail['mastered_count']}/{path_detail['total_nodes']}")
            print(f"  Completion: {path_detail['completion_percentage']}%")
            for n in path_detail["nodes"][:3]:
                print(f"    [{n['status']}] {n['title']} ({n['node_type']})")

        track = ok(await client.get("/me/upselling-track", headers=h1), "upselling track")
        print(f"  Upselling track: {track['mastered_modules']}/{track['total_modules']} mastered, rank #{track['rank_in_department']}")

        # 5. Collaborative Challenges
        challenges = ok(await client.get(f"/challenges?department={USER['department']}", headers=h1), "list challenges")
        print(f"\n[5] Challenges: {len(challenges)} found")
        for c in challenges:
            print(f"  {c['title']} ({c['total_teams']} teams, {c['reward_xp']} XP)")

        if challenges:
            ch = challenges[0]
            ch_detail = ok(await client.get(f"/challenges/{ch['id']}", headers=h1), "challenge detail")
            print(f"  Opened: {ch_detail['title']}")

            # Create team
            team_resp = ok(await client.post(f"/challenges/{ch['id']}/teams", json={"name": "Test Team Alpha"}, headers=h1), "create team")
            print(f"  Created team: {team_resp['name']}")

            # User 2 joins
            join_resp = ok(await client.post(f"/challenges/{ch['id']}/join", json={"team_id": team_resp["id"]}, headers=h2), "join team")
            print(f"  User2 joined: {join_resp['joined']}")

            # Refresh detail
            ch_detail = ok(await client.get(f"/challenges/{ch['id']}", headers=h1), "challenge detail 2")
            for t in ch_detail["teams"]:
                print(f"    Team {t['name']}: {t['member_count']}/{ch_detail['team_size']} members, progress {t['progress']}/{t['target']}")

        # 6. Social
        post_resp = ok(await client.post("/social/posts", json={
            "post_type": "win",
            "body": "Just completed the Sales module! 🎉",
            "ref_type": "module",
            "ref_id": target["id"],
        }, headers=h1), "create post")
        print(f"\n[6] Social: created post {post_resp['id']}")

        # User2 likes the post
        like_resp = ok(await client.post(f"/social/posts/{post_resp['id']}/like", headers=h2), "like post")
        print(f"    User2 liked: {like_resp['liked']}, count={like_resp['like_count']}")

        feed = ok(await client.get("/social/feed?limit=5", headers=h1), "social feed")
        print(f"    Feed: {len(feed)} posts")
        for p in feed[:3]:
            print(f"      [{p['post_type']}] {p['user_name']}: {p['body'][:50]}  ❤️{len(p['likes'])}")

        # Shoutout
        shoutout_resp = ok(await client.post("/social/posts", json={
            "post_type": "shoutout",
            "body": "Great work on onboarding, teammate!",
            "ref_type": "user",
            "ref_id": (await client.get("/auth/me", headers=h2)).json()["id"],
        }, headers=h1), "shoutout")
        print(f"    Shoutout sent!")

        # Check notifications for user2
        notifs = ok(await client.get("/notifications?unread_only=true", headers=h2), "notifications")
        print(f"    User2 notifications: {len(notifs)} unread")
        for n in notifs:
            print(f"      [{n['type']}] {n['title']}")

        # 7. Share achievement
        share = ok(await client.post("/share/achievement", json={"type": "module_mastery", "ref_id": target["id"]}, headers=h1), "share")
        print(f"\n[7] Share: {share['share_text'][:60]}...")

        print("\n" + "=" * 60)
        print("ALL E2E TESTS PASSED")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
