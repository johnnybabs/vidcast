import datetime
import json
import time

import pika

from jsonlog import get_logger

log = get_logger("gateway")


def _record_queued(job_status, fid, username, correlation_id, original_filename,
                   batch_id=None, batch_size=1):
    """Best-effort insert of the UX4 'queued' status doc. Never raises — status
    tracking is a UX nicety and must not fail an upload."""
    if job_status is None:
        return
    try:
        now = datetime.datetime.utcnow()
        job_status.insert_one({
            "video_fid": str(fid),
            "correlation_id": correlation_id,
            "username": username,
            "original_filename": original_filename,
            "status": "queued",
            "created_at": now,
            "updated_at": now,
            "mp3_fid": None,
            # B2: batch grouping. None/1 for single-file uploads — read with
            # .get() everywhere so pre-Sprint-5 docs (no field) stay valid.
            "batch_id": batch_id,
            "batch_size": batch_size,
        })
    except Exception as err:
        log.error("job_status queued insert failed", correlation_id=correlation_id, error=str(err))


def _clear_status(job_status, fid):
    """Remove the queued status doc when the upload is rolled back (the publish or
    outbox write failed and the GridFS object was deleted)."""
    if job_status is None:
        return
    try:
        job_status.delete_one({"video_fid": str(fid)})
    except Exception:
        pass


def upload(f, fs, channel, access, outbox=None, outbox_enabled=False,
           correlation_id="none", job_status=None, batch_id=None, batch_size=1):
    """Store one uploaded video and queue its conversion. Returns
    (video_fid, error) — error is None on success, a short string on failure.
    Each call is one independent job; the batch path (B1) just loops over this."""
    original_filename = getattr(f, "filename", None)
    try:
        # Tag the stored video with its owner (the uploader's JWT email) and a
        # filename. owner_email is what /my-files and the unseen-count badge
        # query on; the converter copies the same tag onto the resulting mp3.
        fid = fs.put(
            f,
            filename=original_filename,
            metadata={"owner_email": access["username"]},
        )
    except Exception as err:
        log.error("GridFS store failed", correlation_id=correlation_id, error=str(err))
        return None, "could not store the file"

    # correlation_id rides in the message body so the converter and notification
    # service log the same id — one upload is greppable across all services (I8/P3).
    # original_filename (UX2) lets the notification email name the file and the
    # converter/UI show it instead of a raw ObjectId. batch_id/batch_size (B2) let
    # the notification service batch-summarise — None/1 for single-file uploads.
    message = {
        "video_fid": str(fid),
        "mp3_fid": None,
        "username": access["username"],
        "correlation_id": correlation_id,
        "original_filename": original_filename,
        "batch_id": batch_id,
        "batch_size": batch_size,
    }

    # UX4: record the job as "queued" so the My Conversions UI can show a status
    # immediately (before any email). Best-effort — status tracking must never
    # break an upload, so a failure here only logs. The converter advances this to
    # "processing"/"ready". Cleaned up below if the publish/outbox then fails.
    _record_queued(job_status, fid, access["username"], correlation_id,
                   original_filename, batch_id=batch_id, batch_size=batch_size)

    # A1 transactional outbox. When OUTBOX_ENABLED is true the gateway does NOT
    # publish to RabbitMQ here — it records the event in the MongoDB `outbox`
    # collection, and the single-replica outbox-relay publishes it asynchronously
    # on its next poll. This guarantees the event survives a broker outage at
    # upload time: the row is durable in Mongo even if RabbitMQ is down, and gets
    # published once the broker recovers. The compensating fs.delete is KEPT as a
    # belt-and-braces fallback (per PHASE_UP_PLAN §7.5) — if the outbox write
    # itself fails, we roll back the orphaned GridFS object, exactly as the
    # direct-publish path does on a broker failure. It is removed only in a clean
    # follow-up once the outbox is proven in a live soak.
    #
    # Consistency note (honest): on the in-cluster mongo:4.0.8 standalone there is
    # no multi-document transaction (that needs a replica set), so the GridFS put
    # and the outbox insert are two sequential writes, not one atomic unit. The
    # ordering (GridFS first, then outbox) plus the compensating delete bounds the
    # failure window to "process crash between the two writes" — which orphans a
    # video with no event, the same window the direct-publish path already has.
    # True atomicity is a documented benefit of managed Mongo (Atlas replica set);
    # see MANAGED_SERVICES.md §3.
    if outbox_enabled and outbox is not None:
        try:
            outbox.insert_one(
                {
                    "event_type": "video.uploaded",
                    "routing_key": "video",
                    "payload": message,
                    "created_at": datetime.datetime.utcnow(),
                    "published_at": None,
                }
            )
        except Exception as err:
            log.error("Outbox write failed", correlation_id=correlation_id, error=str(err))
            fs.delete(fid)
            _clear_status(job_status, fid)
            return None, "could not queue the upload"
        log.info("Upload queued via outbox", correlation_id=correlation_id, video_fid=str(fid))
        return str(fid), None

    # Legacy direct-publish path (OUTBOX_ENABLED=false, the default). Preserved
    # verbatim so behaviour is identical to today when the flag is off.
    try:
        channel.basic_publish(
            exchange="",
            routing_key="video",
            body=json.dumps(message),
            properties=pika.BasicProperties(
                delivery_mode=pika.spec.PERSISTENT_DELIVERY_MODE,
                # B4 SLO 2 clock start: stamp the publish time so the converter can
                # record publish→mp3-write latency. The outbox-relay sets the same
                # property on its publish path, keeping the SLI consistent.
                timestamp=int(time.time()),
            ),
        )
        log.info("Upload published", correlation_id=correlation_id, video_fid=str(fid))
    except Exception as err:
        log.error("RabbitMQ publish failed", correlation_id=correlation_id, error=str(err))
        fs.delete(fid)
        _clear_status(job_status, fid)
        return None, "could not queue the upload"

    return str(fid), None
