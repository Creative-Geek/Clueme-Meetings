"""Chat edit handler - handles editing user messages."""


class EditHandler:
    """Handles editing user messages."""

    def __init__(self, manager):
        self.manager = manager

    def edit(self, bubble_index: int):
        """User edited a message — truncate ChatLog to match."""
        ctx = self.manager.viewed_context
        if ctx:
            ctx.chat_log.truncate_from(bubble_index)
