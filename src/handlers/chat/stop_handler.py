"""Chat stop handler - stops the current AI stream."""


class StopHandler:
    """Handles stopping the current AI stream."""

    def __init__(self, manager):
        self.manager = manager

    def stop(self):
        """Cancel the current AI stream."""
        ctx = self.manager.viewed_context
        if ctx:
            ctx.chat.cancel()
