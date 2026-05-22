"""Chat suggest handler — 'what should I say?' quick action for live Q&A."""

SUGGEST_PROMPT = (
    "Based on what was just said in the meeting, suggest what I should reply. "
    "Use markdown quote to highlight what I should reply."
)


class SuggestHandler:
    """Handles sending a 'what should I say?' prompt to the AI."""

    def __init__(self, send_handler):
        self.send_handler = send_handler

    async def suggest(self):
        """Send the suggest prompt."""
        await self.send_handler.send(SUGGEST_PROMPT)
