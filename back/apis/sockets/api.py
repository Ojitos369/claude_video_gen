# Live job feed: /api/ws/jobs/<job_id> receives the events of one job; /api/ws/jobs/all the status of every job.
from core.bases.apis import WebSocketApi


class JobSocketApi(WebSocketApi):
    async def on_receive(self, data: str):
        if data == "ping":
            await self.websocket.send_text('{"type":"pong"}')
