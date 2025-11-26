import html
from typing import Iterable

import bleach
from markdown_it import MarkdownIt


def _build_renderer() -> MarkdownIt:
    md = MarkdownIt("commonmark", {"linkify": True})
    md.enable("fence")
    md.enable("table")

    fence = md.renderer.rules.get("fence")

    def render_fence(tokens, idx, options, env):
        token = tokens[idx]
        info = (token.info or "").strip()
        if info == "mermaid":
            content = html.escape(token.content)
            return f'<div class="mermaid-container"><button class="mermaid-zoom-btn" title="Zoom diagram"><svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0zM10 7v3m0 0v3m0-3h3m-3 0H7"/></svg></button><pre class="mermaid" data-mermaid-source="{content}">{content}</pre></div>'
        if fence:
            return fence(tokens, idx, options, env)
        return ""

    md.renderer.rules["fence"] = render_fence
    return md


_renderer = _build_renderer()


def _sanitize(html_text: str) -> str:
    allowed_tags = [
        "p",
        "pre",
        "code",
        "span",
        "strong",
        "em",
        "ul",
        "ol",
        "li",
        "blockquote",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "a",
        "table",
        "thead",
        "tbody",
        "tr",
        "th",
        "td",
        "div",
        "button",
        "svg",
        "path",
    ]
    allowed_attrs = {
        "a": ["href", "title"],
        "code": ["class"],
        "pre": ["class", "data-mermaid-source"],
        "div": ["class", "style"],
        "button": ["class", "title", "style"],
        "svg": ["class", "fill", "stroke", "viewBox"],
        "path": ["stroke-linecap", "stroke-linejoin", "stroke-width", "d"],
    }
    return bleach.clean(
        html_text,
        tags=allowed_tags,
        attributes=allowed_attrs,
        strip=True,
    )


def render_markdown(md_text: str) -> str:
    """Return safe HTML from markdown."""
    rendered = _renderer.render(md_text)
    return _sanitize(rendered)
