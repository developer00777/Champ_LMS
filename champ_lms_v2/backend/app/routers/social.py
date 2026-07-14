from typing import Annotated
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from beanie.operators import In, Set, Push
from app.core.auth import get_current_user
from app.models.user import User
from app.models.social import SocialPost, Notification

router = APIRouter(tags=["social"])


class CreatePostBody(BaseModel):
    post_type: str = "win"  # win | shoutout | help | milestone
    body: str
    team_id: str | None = None
    ref_type: str | None = None
    ref_id: str | None = None


@router.get("/social/feed")
async def social_feed(
    user: Annotated[User, Depends(get_current_user)],
    department: str | None = None,
    limit: int = 30,
):
    posts = await SocialPost.find_all().sort(-SocialPost.created_at).limit(limit).to_list()
    user_ids = list({p.user_id for p in posts})
    users = {u.id: u for u in await User.find(In(User.id, user_ids)).to_list()} if user_ids else {}

    result = []
    for p in posts:
        u = users.get(p.user_id)
        if not u:
            continue
        if department and u.department != department:
            continue
        result.append({
            "id": p.id,
            "post_type": p.post_type,
            "body": p.body,
            "user_id": p.user_id,
            "user_name": u.full_name,
            "user_department": u.department,
            "team_id": p.team_id,
            "ref_type": p.ref_type,
            "ref_id": p.ref_id,
            "likes": p.likes,
            "liked_by_me": user.id in p.likes,
            "created_at": p.created_at.isoformat(),
        })
    return result


@router.post("/social/posts", status_code=201)
async def create_post(
    body: CreatePostBody,
    user: Annotated[User, Depends(get_current_user)],
):
    post = SocialPost(
        user_id=user.id,
        team_id=body.team_id,
        post_type=body.post_type,
        body=body.body,
        ref_type=body.ref_type,
        ref_id=body.ref_id,
    )
    await post.insert()

    # * If shoutout, create a notification for the mentioned user (by ref_id = user_id)
    if body.post_type == "shoutout" and body.ref_id:
        await Notification(
            user_id=body.ref_id,
            notif_type="shoutout",
            title=f"{user.full_name or 'Someone'} gave you a shoutout!",
            body=body.body,
            ref_type="social_post",
            ref_id=post.id,
        ).insert()

    return {"id": post.id, "created": True}


@router.post("/social/posts/{post_id}/like")
async def toggle_like(
    post_id: str,
    user: Annotated[User, Depends(get_current_user)],
):
    post = await SocialPost.get(post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    if user.id in post.likes:
        post.likes = [uid for uid in post.likes if uid != user.id]
    else:
        post.likes.append(user.id)
    await post.save()
    return {"liked": user.id in post.likes, "like_count": len(post.likes)}


@router.get("/notifications")
async def my_notifications(
    user: Annotated[User, Depends(get_current_user)],
    unread_only: bool = False,
    limit: int = 30,
):
    filters = [Notification.user_id == user.id]
    if unread_only:
        filters.append(Notification.read == False)  # noqa: E712
    notifs = await Notification.find(*filters).sort(-Notification.created_at).limit(limit).to_list()
    return [
        {
            "id": n.id,
            "type": n.notif_type,
            "title": n.title,
            "body": n.body,
            "ref_type": n.ref_type,
            "ref_id": n.ref_id,
            "read": n.read,
            "created_at": n.created_at.isoformat(),
        }
        for n in notifs
    ]


@router.post("/notifications/{notif_id}/read")
async def mark_read(
    notif_id: str,
    user: Annotated[User, Depends(get_current_user)],
):
    notif = await Notification.get(notif_id)
    if not notif or notif.user_id != user.id:
        raise HTTPException(status_code=404, detail="Notification not found")
    notif.read = True
    await notif.save()
    return {"read": True}


@router.post("/notifications/read-all")
async def mark_all_read(user: Annotated[User, Depends(get_current_user)]):
    unread = await Notification.find(
        Notification.user_id == user.id,
        Notification.read == False,  # noqa: E712
    ).to_list()
    for n in unread:
        n.read = True
        await n.save()
    return {"marked_read": len(unread)}
