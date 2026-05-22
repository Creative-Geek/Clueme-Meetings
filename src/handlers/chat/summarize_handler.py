"""Chat summarize handler - sends a summarize prompt to the AI."""

SUMMARIZE_PROMPT = (
    "Summarize the meeting so far as atomic self contained facts (excluding anything you "
    "already summarized)."
)


class SummarizeHandler:
    """Handles sending a summarize prompt to the AI."""

    def __init__(self, send_handler):
        self.send_handler = send_handler

    async def summarize(self):
        """Send the summarize prompt."""
        await self.send_handler.send(SUMMARIZE_PROMPT)
