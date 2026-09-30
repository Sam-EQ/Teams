import time
from pathlib import Path

import httpx

from app.core.config import (
    TEAMS_CLIENT_ID,
    TEAMS_CLIENT_SECRET,
    TEAMS_GRAPH_URL,
    TEAMS_LOGIN_URL,
    TEAMS_ORGANIZER_ID,
    TEAMS_TENANT_ID,
)
from app.core.errors import MeetingNotFound, RecordingNotReady, TeamsError


def check(response: httpx.Response, action: str):
    if response.is_error:
        raise TeamsError(f"{action} failed with {response.status_code}: {response.text[:300]}")


def latest(items: list[dict]) -> dict:
    return max(items, key=lambda item: item.get("createdDateTime", ""))


class TeamsClient:
    def __init__(self):
        self.http = httpx.AsyncClient(timeout=httpx.Timeout(60, read=600), follow_redirects=True)
        self.meetings_url = f"{TEAMS_GRAPH_URL}/users/{TEAMS_ORGANIZER_ID}/onlineMeetings"
        self.token = None
        self.expires_at = 0.0

    async def close(self):
        await self.http.aclose()

    async def _headers(self) -> dict:
        if not self.token or time.monotonic() > self.expires_at - 60:
            response = await self.http.post(
                f"{TEAMS_LOGIN_URL}/{TEAMS_TENANT_ID}/oauth2/v2.0/token",
                data={
                    "client_id": TEAMS_CLIENT_ID,
                    "client_secret": TEAMS_CLIENT_SECRET,
                    "scope": "https://graph.microsoft.com/.default",
                    "grant_type": "client_credentials",
                },
            )
            check(response, "token request")
            body = response.json()
            self.token = body["access_token"]
            self.expires_at = time.monotonic() + float(body.get("expires_in", 3600))
        return {"Authorization": f"Bearer {self.token}"}

    async def _get(self, path: str, params: dict | None = None) -> httpx.Response:
        response = await self.http.get(f"{self.meetings_url}{path}", params=params, headers=await self._headers())
        check(response, f"GET onlineMeetings{path}")
        return response

    async def find_meeting(self, join_url: str) -> tuple[str, str]:
        meetings = (await self._get("", {"$filter": f"JoinWebUrl eq '{join_url}'"})).json()["value"]
        if not meetings:
            raise MeetingNotFound("no meeting found for this join link, check the link and that the configured organiser scheduled it")
        return meetings[0]["id"], meetings[0].get("subject") or "teams-meeting"

    async def latest_recording(self, meeting_id: str) -> str:
        recordings = (await self._get(f"/{meeting_id}/recordings")).json()["value"]
        if not recordings:
            raise RecordingNotReady("meeting has no recording yet, it may still be processing")
        return latest(recordings)["id"]

    async def download_recording(self, meeting_id: str, recording_id: str, dst: Path):
        url = f"{self.meetings_url}/{meeting_id}/recordings/{recording_id}/content"
        async with self.http.stream("GET", url, headers=await self._headers()) as response:
            if response.is_error:
                await response.aread()
                check(response, "recording download")
            with dst.open("wb") as out:
                async for chunk in response.aiter_bytes():
                    out.write(chunk)

    async def transcript(self, meeting_id: str) -> str | None:
        transcripts = (await self._get(f"/{meeting_id}/transcripts")).json()["value"]
        if not transcripts:
            return None
        response = await self._get(f"/{meeting_id}/transcripts/{latest(transcripts)['id']}/content", {"$format": "text/vtt"})
        return response.text
