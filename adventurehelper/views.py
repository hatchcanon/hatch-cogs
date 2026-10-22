from typing import Optional

import discord


def text_view(content: str) -> discord.ui.LayoutView:
    """A components v2 message holding plain text."""
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(discord.ui.TextDisplay(content))
    return view


def container_view(
    *sections: str, title: Optional[str] = None, colour: Optional[discord.Colour] = None
) -> discord.ui.LayoutView:
    """A components v2 message with text sections in a container, split by separators."""
    container = discord.ui.Container(accent_colour=colour)
    if title:
        container.add_item(discord.ui.TextDisplay(f"### {title}"))
    for i, section in enumerate(sections):
        if i:
            container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(section))
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(container)
    return view


def image_view(file: discord.File) -> discord.ui.LayoutView:
    """A components v2 message showing an attached image. Send `file` alongside it."""
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(discord.ui.MediaGallery(discord.MediaGalleryItem(f"attachment://{file.filename}")))
    return view
