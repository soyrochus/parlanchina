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
            return f'<pre class="mermaid">{content}</pre>'
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
    ]
    allowed_attrs = {
        "a": ["href", "title"],
        "code": ["class"],
        "pre": ["class"],
        "div": ["class"],
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
