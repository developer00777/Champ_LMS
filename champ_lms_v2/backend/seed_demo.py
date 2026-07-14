"""
# Local demo seed: publishes a handful of modules + episodes so the Netflix
# feed and gamification surfaces render with real content. Idempotent.
"""
import asyncio
from app.core.db import init_db
from app.models.module import Module
from app.models.episode import Episode
from app.models.learning_path import LearningPath

MODULES = [
    ("Closing the Deal: Objection Handling", "sales", ["sales", "account-exec"]),
    ("Prospecting That Actually Converts", "sales", ["sales"]),
    ("Your First Week: Company 101", "onboarding", ["all"]),
    ("Coaching Your Team to Ownership", "leadership", ["manager"]),
    ("Async Communication Mastery", "engineering", ["engineer"]),
    ("Reading a P&L in Ten Minutes", "finance", ["all"]),
    ("Product Roadmap Prioritization", "product", ["product", "pm"]),
    ("Customer Discovery Interviews", "product", ["product"]),
    ("Ops Runbook: Incident Response", "ops", ["ops", "sre"]),
    ("Supply Chain Fundamentals", "ops", ["ops"]),
]

# * Learning path definitions: onboarding=trail variant, upskilling=ridge variant
DEPT_PATHS = [
    ("sales", "Your First 30 Days in Sales", "onboarding", "trail"),
    ("sales", "Sales Mastery Ascent", "upskilling", "ridge"),
    ("leadership", "New Leader Foundations", "onboarding", "trail"),
    ("leadership", "Leadership Summit", "upskilling", "ridge"),
    ("onboarding", "Company 101 Trail", "onboarding", "trail"),
    ("product", "Product Team Onboarding", "onboarding", "trail"),
    ("product", "Product Craft Ridge", "upskilling", "ridge"),
    ("engineering", "Eng Onboarding Path", "onboarding", "trail"),
    ("engineering", "Engineering Mastery Climb", "upskilling", "ridge"),
    ("ops", "Ops Foundations Trail", "onboarding", "trail"),
    ("ops", "Operations Excellence Ridge", "upskilling", "ridge"),
]


async def seed_paths() -> None:
    """Create learning paths from department modules. Idempotent by key."""
    for dept, title, ptype, variant in DEPT_PATHS:
        key = f"{dept}_{ptype}"
        existing = await LearningPath.find_one(LearningPath.key == key)
        if existing:
            continue
        # Find modules for this department
        modules = await Module.find(
            Module.is_published == True,  # noqa: E712
            Module.category == dept,
        ).sort(+Module.created_at).to_list()
        if not modules:
            continue
        nodes = []
        for i, m in enumerate(modules):
            node_type = "video"
            is_summit = (i == len(modules) - 1)
            if is_summit:
                node_type = "summit"
            elif i > 0 and i % 2 == 0:
                node_type = "milestone"
            nodes.append({
                "sequence": i,
                "module_id": m.id,
                "node_type": node_type,
                "unlock_rule": "previous",
                "is_summit": is_summit,
                "title": m.title,
            })
        path = LearningPath(
            key=key,
            title=title,
            description=f"{dept.capitalize()} {ptype} path with {len(nodes)} checkpoints.",
            department=dept,
            path_type=ptype,
            variant=variant,
            nodes=nodes,
            total_modules=len(modules),
        )
        await path.insert()
        print(f"  path: {key} ({len(nodes)} nodes)")


async def main() -> None:
    await init_db()
    if await Module.find(Module.is_published == True).count() > 0:  # noqa: E712
        print("modules already seeded")
    else:
        for title, cat, roles in MODULES:
            m = Module(
                title=title,
                description=f"A {cat} micro-series. Short, binge-worthy lessons you finish on a coffee break.",
                category=cat,
                tags=[cat, "micro"],
                target_roles=roles,
                source_type="manual",
                is_published=True,
                total_episodes=3,
            )
            await m.insert()
            head = title.split(":")[0]
            for i in range(1, 4):
                await Episode(
                    module_id=m.id,
                    title=f"{i}. {head} — part {i}",
                    description="~5 min lesson",
                    duration_seconds=300,
                    sequence_order=i,
                    status="ready",
                ).insert()
        print("seeded", await Module.count(), "modules,", await Episode.count(), "episodes")
    await seed_paths()
    print("paths:", await LearningPath.count())


if __name__ == "__main__":
    asyncio.run(main())
