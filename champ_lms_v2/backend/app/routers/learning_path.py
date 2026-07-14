from typing import Annotated
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from beanie.operators import In, Set
from app.core.auth import get_current_user
from app.models.user import User
from app.models.module import Module
from app.models.enrollment import Enrollment
from app.models.learning_path import LearningPath, UserPathProgress
from app.services.bunny_storage import bunny_storage

router = APIRouter(tags=["learning_paths"])


@router.get("/paths")
async def list_paths(
    user: Annotated[User, Depends(get_current_user)],
    department: str | None = None,
    path_type: str | None = None,
):
    filters = [LearningPath.is_active == True]  # noqa: E712
    if department:
        filters.append(LearningPath.department == department)
    if path_type:
        filters.append(LearningPath.path_type == path_type)

    paths = await LearningPath.find(*filters).to_list()
    return [
        {
            "id": p.id,
            "key": p.key,
            "title": p.title,
            "description": p.description,
            "department": p.department,
            "path_type": p.path_type,
            "variant": p.variant,
            "total_modules": p.total_modules,
            "total_nodes": len(p.nodes),
        }
        for p in paths
    ]


@router.get("/paths/{path_id}")
async def get_path(
    path_id: str,
    user: Annotated[User, Depends(get_current_user)],
):
    path = await LearningPath.get(path_id)
    if not path:
        raise HTTPException(status_code=404, detail="Learning path not found")

    # Get or create user progress
    progress = await UserPathProgress.find_one(
        UserPathProgress.user_id == user.id,
        UserPathProgress.path_id == path_id,
    )
    if not progress:
        progress = UserPathProgress(user_id=user.id, path_id=path_id, unlocked_nodes=[0])
        await progress.insert()

    # Hydrate nodes with module data + enrollment status
    module_ids = [n["module_id"] for n in path.nodes if n.get("module_id")]
    modules = {m.id: m for m in await Module.find(In(Module.id, module_ids)).to_list()} if module_ids else {}
    enrollments = {
        e.module_id: e
        for e in await Enrollment.find(
            Enrollment.user_id == user.id,
            In(Enrollment.module_id, module_ids),
        ).to_list()
    } if module_ids else {}

    nodes_out = []
    for i, node in enumerate(path.nodes):
        mid = node.get("module_id")
        mod = modules.get(mid)
        enr = enrollments.get(mid)
        status = "locked"
        if i in progress.mastered_nodes:
            status = "mastered"
        elif i == progress.current_node or i in progress.unlocked_nodes:
            if enr and enr.completion_percentage >= 100:
                status = "completed"
            elif enr and enr.completion_percentage > 0:
                status = "in_progress"
            else:
                status = "unlocked"
        nodes_out.append({
            "sequence": i,
            "module_id": mid,
            "node_type": node.get("node_type", "video"),
            "unlock_rule": node.get("unlock_rule", "previous"),
            "is_summit": node.get("is_summit", False),
            "title": node.get("title") or (mod.title if mod else f"Node {i+1}"),
            "module_title": mod.title if mod else None,
            "module_category": mod.category if mod else None,
            "thumbnail_url": bunny_storage.thumbnail_url(mod.thumbnail_bunny_path) if mod and mod.thumbnail_bunny_path else None,
            "total_episodes": mod.total_episodes if mod else 0,
            "progress_pct": enr.completion_percentage if enr else 0,
            "mastered": bool(enr and enr.completed_at),
            "status": status,
        })

    total = len(nodes_out)
    mastered_count = len(progress.mastered_nodes)
    completion_pct = round((mastered_count / total) * 100, 2) if total else 0

    return {
        "id": path.id,
        "key": path.key,
        "title": path.title,
        "description": path.description,
        "department": path.department,
        "path_type": path.path_type,
        "variant": path.variant,
        "nodes": nodes_out,
        "current_node": progress.current_node,
        "unlocked_nodes": progress.unlocked_nodes,
        "mastered_nodes": progress.mastered_nodes,
        "total_nodes": total,
        "mastered_count": mastered_count,
        "completion_percentage": completion_pct,
        "started_at": progress.started_at.isoformat(),
        "completed_at": progress.completed_at.isoformat() if progress.completed_at else None,
    }


@router.post("/paths/{path_id}/enroll")
async def enroll_in_path(
    path_id: str,
    user: Annotated[User, Depends(get_current_user)],
):
    path = await LearningPath.get(path_id)
    if not path:
        raise HTTPException(status_code=404, detail="Learning path not found")
    progress = await UserPathProgress.find_one(
        UserPathProgress.user_id == user.id,
        UserPathProgress.path_id == path_id,
    )
    if not progress:
        progress = UserPathProgress(user_id=user.id, path_id=path_id, unlocked_nodes=[0])
        await progress.insert()
    return {"enrolled": True, "path_id": path_id}


@router.post("/paths/{path_id}/advance")
async def advance_path_node(
    path_id: str,
    user: Annotated[User, Depends(get_current_user)],
):
    """Called after a module is mastered. Advances current_node and unlocks next."""
    path = await LearningPath.get(path_id)
    if not path:
        raise HTTPException(status_code=404, detail="Learning path not found")

    progress = await UserPathProgress.find_one(
        UserPathProgress.user_id == user.id,
        UserPathProgress.path_id == path_id,
    )
    if not progress:
        progress = UserPathProgress(user_id=user.id, path_id=path_id, unlocked_nodes=[0])
        await progress.insert()

    current = progress.current_node
    nodes = path.nodes

    # Mark current as mastered if not already
    if current not in progress.mastered_nodes:
        progress.mastered_nodes.append(current)

    # Unlock next node
    next_node = current + 1
    if next_node < len(nodes):
        if next_node not in progress.unlocked_nodes:
            progress.unlocked_nodes.append(next_node)
        progress.current_node = next_node
    else:
        # Path complete
        progress.completed_at = datetime.now(timezone.utc)

    await progress.save()

    return {
        "current_node": progress.current_node,
        "unlocked_nodes": progress.unlocked_nodes,
        "mastered_nodes": progress.mastered_nodes,
        "completed": progress.completed_at is not None,
    }
