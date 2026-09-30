"""
Bunny Stream webhook receiver.
Replaces EventBridge + Lambda mediaconvert_completion from v1.

Bunny calls POST /webhooks/bunny-stream when video encoding completes.
We update the episode status to 'ready' and set duration_seconds.
"""
from fastapi import APIRouter, Request, HTTPException
from app.models.episode import Episode
from app.services.bunny_stream import bunny_stream
from app.services.clips import apply_source_length

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/bunny-stream")
async def bunny_stream_webhook(request: Request):
    """
    Bunny Stream sends this on video status changes.
    Relevant status: 4 = finished encoding.

    Headers:
      BunnyVideo-Signature: SHA256 HMAC of payload
    """
    body = await request.body()
    # Bunny Stream sends the library API key in the 'AccessKey' header (not HMAC)
    access_key = request.headers.get("AccessKey", "")

    if not bunny_stream.verify_webhook_signature(body, access_key):
        raise HTTPException(status_code=401, detail="Invalid Bunny webhook signature")

    payload = await request.json()
    video_guid = payload.get("VideoGuid") or payload.get("videoGuid")
    status = payload.get("Status")  # 4 = Finished
    duration = payload.get("Length")  # seconds

    if not video_guid:
        return {"ignored": True}

    # Every episode playing this video: a split video is several episodes, each
    # a part of the same Bunny video, and all of them become ready together.
    episodes = await Episode.find(Episode.bunny_video_guid == video_guid).to_list()
    if not episodes:
        return {"ignored": True, "reason": "no episode found for guid"}

    thumbnail_url = None
    if status == 4:  # Finished
        # Fetch thumbnail from Bunny Stream auto-generated thumbnail
        try:
            video_info = await bunny_stream.get_video(video_guid)
            thumbnail_file = video_info.get("thumbnailFileName")
            if thumbnail_file:
                thumbnail_url = bunny_stream.get_thumbnail_url(video_guid, thumbnail_file)
        except Exception:
            pass  # Thumbnail fetch is non-critical

    for ep in episodes:
        if status == 4:
            ep.status = "ready"
            apply_source_length(ep, duration)
            if thumbnail_url:
                ep.thumbnail_url = thumbnail_url
        elif status == 5:  # Failed
            ep.status = "failed"
        await ep.save()
    ep = episodes[0]

    return {"processed": True, "video_guid": video_guid, "new_status": ep.status}
