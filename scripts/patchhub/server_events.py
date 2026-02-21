from __future__ import annotations

import json
import time
from typing import Any


def _api_jobs_events(self, job_id: str) -> None:
    job = self.app.queue.get_job(job_id)

    disk_job = None
    if job is None:
        disk_job = self.app._load_job_from_disk(job_id)

    if job is None and disk_job is None:
        # Do not return 404: EventSource will retry forever.
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        data = json.dumps({"reason": "job_not_found"}, ensure_ascii=True)
        self.wfile.write(f"event: end\ndata: {data}\n\n".encode())
        self.wfile.flush()
        return

    if disk_job is not None and job is None:
        jsonl_path = self.app._job_jsonl_path_from_fields(
            job_id=str(job_id),
            mode=str(disk_job.mode),
            issue_id=str(disk_job.issue_id),
        )
    else:
        assert job is not None
        jsonl_path = self.app._job_jsonl_path(job)

    self.send_response(200)
    self.send_header("Content-Type", "text/event-stream; charset=utf-8")
    self.send_header("Cache-Control", "no-cache")
    self.send_header("Connection", "keep-alive")
    self.end_headers()

    def send_line(line: str) -> None:
        self.wfile.write(line.encode("utf-8", errors="replace"))
        self.wfile.flush()

    def send_end(reason: str, status: str | None = None) -> None:
        payload: dict[str, Any] = {"reason": reason}
        if status is not None:
            payload["status"] = status
        data = json.dumps(payload, ensure_ascii=True)
        send_line("event: end\n")
        send_line("data: " + data + "\n\n")

    last_ping = time.monotonic()
    offset = 0
    last_growth = time.monotonic()

    while True:
        try:
            # Wait for the JSONL file to appear (runner creates it early, but not instantly).
            if not jsonl_path.exists():
                job_now = self.app.queue.get_job(job_id)
                if job_now is None:
                    if disk_job is not None:
                        send_end("job_completed", status=str(disk_job.status))
                        return
                    send_end("job_not_found")
                    return
                if job_now.status != "running":
                    send_end("job_completed", status=str(job_now.status))
                    return
                time.sleep(0.2)
                continue

            with jsonl_path.open("rb") as fp:
                fp.seek(offset)
                chunk = fp.read()
                if chunk:
                    last_growth = time.monotonic()
                    # We only emit complete lines. Keep partial trailing bytes for next pass.
                    parts = chunk.split(b"\n")
                    if chunk.endswith(b"\n"):
                        complete = parts[:-1]
                        tail = b""
                    else:
                        complete = parts[:-1]
                        tail = parts[-1]
                    for raw in complete:
                        raw = raw.strip()
                        if not raw:
                            continue
                        try:
                            s = raw.decode("utf-8")
                        except Exception:
                            s = raw.decode("utf-8", errors="replace")
                        send_line(f"data: {s}\n\n")
                    offset = fp.tell() - len(tail)

            now = time.monotonic()
            if now - last_ping >= 10.0:
                send_line(": ping\n\n")
                last_ping = now

            job_now = self.app.queue.get_job(job_id)
            if job_now is None:
                if disk_job is not None:
                    send_end("job_completed", status=str(disk_job.status))
                    return
                send_end("job_not_found")
                return

            if job_now.status != "running" and now - last_growth >= 0.5:
                # If nothing new has arrived shortly after completion, end the stream.
                send_end("job_completed", status=str(job_now.status))
                return

            time.sleep(0.2)
        except (BrokenPipeError, ConnectionResetError):
            return
        except FileNotFoundError:
            # The JSONL file may be rotated/removed; end deterministically.
            job_now = self.app.queue.get_job(job_id)
            if job_now is not None:
                send_end("job_completed", status=str(job_now.status))
            elif disk_job is not None:
                send_end("job_completed", status=str(disk_job.status))
            else:
                send_end("io_error")
            return
        except OSError:
            send_end("io_error")
            return
