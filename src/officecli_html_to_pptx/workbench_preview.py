"""Ephemeral, source-mapped Preview products for the Workbench.

The Preview is deliberately a small adapter around the real Author HTML.  It
never becomes a compiler input: markers, the navigation script, the resource
base, and the isolated-frame policy are added to a transient copy only.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from html.parser import HTMLParser
import mimetypes
from pathlib import Path
import re
from typing import Any
from urllib.parse import quote, unquote, urlsplit


_VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}
_TEXT_TAGS = {
    "a",
    "blockquote",
    "code",
    "dd",
    "dt",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "label",
    "li",
    "p",
    "pre",
    "span",
    "td",
    "th",
}
_URL_ATTRIBUTES = {
    "action",
    "cite",
    "formaction",
    "href",
    "poster",
    "src",
    "xlink:href",
}
_LOCAL_RESOURCE_SUFFIXES = {
    ".avif",
    ".bmp",
    ".css",
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".png",
    ".svg",
    ".ttf",
    ".woff",
    ".woff2",
    ".webp",
}
_EVENT_ATTRIBUTE_RE = re.compile(
    r"\s+on[\w:-]+\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+)",
    re.IGNORECASE | re.DOTALL,
)
_MARKER_ATTRIBUTE_RE = re.compile(
    r"\s+data-workbench-marker\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+)",
    re.IGNORECASE | re.DOTALL,
)
_ATTRIBUTE_RE = re.compile(
    r"(?P<space>\s+)(?P<name>[\w:-]+)(?P<equals>\s*=\s*)(?P<quote>[\"'])(?P<value>.*?)\4",
    re.IGNORECASE | re.DOTALL,
)
_UNQUOTED_ATTRIBUTE_RE = re.compile(
    r"(?P<space>\s+)(?P<name>[\w:-]+)(?P<equals>\s*=\s*)(?P<value>[^\s\"'=<>`]+)",
    re.IGNORECASE,
)
_CSS_URL_RE = re.compile(
    r"url\(\s*(?:(?P<double>\"[^\"]*\")|(?P<single>'[^']*')|(?P<bare>[^)]*))\s*\)",
    re.IGNORECASE | re.DOTALL,
)


@dataclass(frozen=True)
class PreviewMapEntry:
    marker: str
    kind: str
    tag: str
    slide: int | None
    source_start: int | None
    source_end: int | None
    editor_start: int | None
    editor_end: int | None
    line: int | None
    column: int | None
    status: str
    reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "marker": self.marker,
            "kind": self.kind,
            "tag": self.tag,
            "slide": self.slide,
            "source_start": self.source_start,
            "source_end": self.source_end,
            "editor_start": self.editor_start,
            "editor_end": self.editor_end,
            "line": self.line,
            "column": self.column,
            "status": self.status,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class PreviewProduct:
    """One immutable Preview response produced from one draft revision."""

    html: str
    source_map: dict[str, dict[str, Any]]
    slide_count: int
    slides: tuple[dict[str, Any], ...]
    blocked_resources: tuple[dict[str, str], ...]
    parser_repaired: bool
    aspect_ratio: str = "16:9"

    def selection(self, marker: str) -> dict[str, Any]:
        entry = self.source_map.get(marker)
        if entry is None:
            return {"status": "unmapped", "marker": marker, "reason": "unknown_marker"}
        return dict(entry)


@dataclass
class _StartEvent:
    tag: str
    raw: str
    start: int
    end: int
    attrs: dict[str, str | None]
    slide: int | None
    self_closing: bool
    inside_special: bool
    has_element_child: bool = False
    has_text: bool = False


def _line_offsets(text: str) -> list[int]:
    offsets = [0]
    for match in re.finditer(r"\n", text):
        offsets.append(match.end())
    return offsets


def _editor_offset(text: str) -> int:
    """Convert a Python code-point offset to a browser textarea offset."""
    return len(text.encode("utf-16-le")) // 2


class _SourceParser(HTMLParser):
    """Collect source-token positions while noting browser-repair hazards."""

    def __init__(self, text: str) -> None:
        super().__init__(convert_charrefs=False)
        self.text = text
        self.offsets = _line_offsets(text)
        self.events: list[_StartEvent] = []
        self.stack: list[tuple[str, bool, int | None, int]] = []
        self.slide_count = 0
        self.current_slide: int | None = None
        self.repaired = False
        self.head_end: int | None = None
        self.body_end: int | None = None
        self.style_data: list[tuple[int, int]] = []

    def _offset(self) -> int:
        line, column = self.getpos()
        if line <= 0 or line > len(self.offsets):
            self.repaired = True
            return 0
        return self.offsets[line - 1] + column

    @staticmethod
    def _attrs_dict(attrs: list[tuple[str, str | None]]) -> dict[str, str | None]:
        # Duplicate attributes are parser-repaired by browsers; retaining one
        # value would make a source click untrustworthy.
        result: dict[str, str | None] = {}
        for key, value in attrs:
            lowered = key.lower()
            if lowered in result:
                result[f"__duplicate__{lowered}"] = value
            else:
                result[lowered] = value
        return result

    def _record_start(self, tag: str, attrs: list[tuple[str, str | None]], *, self_closing: bool) -> None:
        raw = self.get_starttag_text() or ""
        start = self._offset()
        end = start + len(raw)
        lowered = tag.lower()
        attrs_dict = self._attrs_dict(attrs)
        if any(key.startswith("__duplicate__") for key in attrs_dict):
            self.repaired = True
        if self.stack:
            self.events[self.stack[-1][3]].has_element_child = True
        slide = self.current_slide
        if "slide" in set((attrs_dict.get("class") or "").split()):
            self.slide_count += 1
            self.current_slide = self.slide_count
            slide = self.current_slide
        is_special = (
            attrs_dict.get("data-pptx-rasterize") == "localized"
            or "data-pptx-chart" in attrs_dict
            or "data-pptx-shape-geometry" in attrs_dict
            or lowered in {"table", "picture", "svg"}
        )
        self.events.append(
            _StartEvent(
                tag=lowered,
                raw=raw,
                start=start,
                end=end,
                attrs=attrs_dict,
                slide=slide,
                self_closing=self_closing,
                inside_special=any(is_special for _, is_special, _, _ in self.stack),
            )
        )
        event_index = len(self.events) - 1
        if lowered == "head":
            self.head_end = end
        if lowered not in _VOID_TAGS and not self_closing:
            self.stack.append((lowered, is_special, self.current_slide, event_index))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._record_start(tag, attrs, self_closing=False)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._record_start(tag, attrs, self_closing=True)

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered == "body":
            self.body_end = self._offset()
        if lowered in _VOID_TAGS:
            self.repaired = True
            return
        if not self.stack or self.stack[-1][0] != lowered:
            self.repaired = True
            stack_tags = [item[0] for item in self.stack]
            if lowered in stack_tags:
                del self.stack[stack_tags.index(lowered) :]
            return
        _, _, parent_slide, _ = self.stack.pop()
        self.current_slide = parent_slide

    def handle_data(self, data: str) -> None:
        if self.stack and self.stack[-1][0] == "style":
            start = self._offset()
            self.style_data.append((start, start + len(data)))
        elif self.stack and data.strip():
            self.events[self.stack[-1][3]].has_text = True

    def finish(self) -> None:
        if self.stack:
            self.repaired = True


def _kind_for(event: _StartEvent) -> str | None:
    attrs = event.attrs
    if event.inside_special:
        return None
    if event.tag in {"html", "head", "body", "style", "script", "meta", "link", "base"}:
        return None
    if attrs.get("data-pptx-rasterize") == "localized":
        return "localized-fallback"
    if "data-pptx-chart" in attrs:
        return "chart"
    if "data-pptx-shape-geometry" in attrs:
        return "shape"
    if event.tag in {"img", "picture", "svg"}:
        return "picture"
    if event.tag == "table":
        return "table"
    if event.tag in _TEXT_TAGS or (event.tag == "div" and event.has_text and not event.has_element_child):
        return "text"
    return None


def _quoted_attribute_value(value: str) -> str:
    return escape(value, quote=True)


def _is_data_resource(value: str) -> bool:
    lowered = value.strip().lower()
    return lowered.startswith("data:image/") or lowered.startswith("data:font/")


def _file_url_relative(value: str, asset_root: Path) -> str | None:
    parsed = urlsplit(value)
    if parsed.scheme.lower() != "file":
        return None
    raw_path = unquote(parsed.path)
    if parsed.netloc and parsed.netloc not in {"", "localhost"}:
        raw_path = f"//{parsed.netloc}{raw_path}"
    if asset_root.drive and raw_path.startswith("/") and len(raw_path) >= 3 and raw_path[2] == ":":
        raw_path = raw_path[1:]
    try:
        candidate = Path(raw_path).resolve()
        relative = candidate.relative_to(asset_root.resolve())
    except (OSError, ValueError):
        return None
    if not candidate.is_file():
        return None
    return relative.as_posix()


def _resource_url(
    value: str,
    *,
    asset_root: Path,
    base_url: str,
    blocked: list[dict[str, str]],
    context: str,
) -> str:
    stripped = value.strip().strip("\"'")
    if not stripped or stripped.startswith("#"):
        return value
    lowered = stripped.lower()
    if _is_data_resource(stripped):
        return value
    if lowered.startswith("data:"):
        blocked.append({"value": stripped, "context": context, "reason": "data_type_not_allowed"})
        return "about:blank"
    if lowered.startswith("javascript:"):
        blocked.append({"value": stripped, "context": context, "reason": "javascript_url"})
        return "about:blank"
    parsed = urlsplit(stripped)
    if parsed.scheme.lower() in {"http", "https", "ftp", "ws", "wss"} or parsed.netloc:
        blocked.append({"value": stripped, "context": context, "reason": "public_network"})
        return "about:blank"
    if parsed.scheme.lower() == "file":
        relative = _file_url_relative(stripped, asset_root)
        if relative is None:
            blocked.append({"value": stripped, "context": context, "reason": "outside_authorized_root"})
            return "about:blank"
        return f"{base_url}{quote(relative, safe='/')}"
    # Resolve relative resource attributes before the document reaches the
    # sandbox.  A query string on <base> is not retained by browser URL
    # resolution, so absolute session-bound URLs are used for deterministic
    # local assets instead.
    raw_path = unquote(parsed.path)
    try:
        candidate = (asset_root / Path(raw_path)).resolve()
        relative = candidate.relative_to(asset_root.resolve())
    except (OSError, ValueError):
        blocked.append({"value": stripped, "context": context, "reason": "outside_authorized_root"})
        return "about:blank"
    if not candidate.is_file():
        blocked.append({"value": stripped, "context": context, "reason": "resource_not_found"})
        return "about:blank"
    suffix = ""
    if parsed.query:
        suffix += f"?{parsed.query}"
    if parsed.fragment:
        suffix += f"#{parsed.fragment}"
    return f"{base_url}{quote(relative.as_posix(), safe='/')}{suffix}"


def _sanitize_css(
    value: str,
    *,
    asset_root: Path,
    base_url: str,
    blocked: list[dict[str, str]],
) -> str:
    def replace(match: re.Match[str]) -> str:
        raw = next((match.group(name) for name in ("double", "single", "bare") if match.group(name) is not None), "")
        unquoted = raw[1:-1] if len(raw) >= 2 and raw[0] in "\"'" and raw[-1] == raw[0] else raw
        safe = _resource_url(
            unquoted,
            asset_root=asset_root,
            base_url=base_url,
            blocked=blocked,
            context="style",
        )
        return f"url('{safe}')"

    return _CSS_URL_RE.sub(replace, value)


def _sanitize_srcset(
    value: str,
    *,
    asset_root: Path,
    base_url: str,
    blocked: list[dict[str, str]],
) -> str:
    candidates: list[str] = []
    for item in value.split(","):
        parts = item.strip().split(None, 1)
        if not parts:
            continue
        safe = _resource_url(
            parts[0],
            asset_root=asset_root,
            base_url=base_url,
            blocked=blocked,
            context="srcset",
        )
        candidates.append(safe if len(parts) == 1 else f"{safe} {parts[1]}")
    return ", ".join(candidates)


def _sanitize_start_tag(
    event: _StartEvent,
    *,
    asset_root: Path,
    base_url: str,
    blocked: list[dict[str, str]],
) -> str:
    blocked_script = event.tag == "script" and "json" not in (event.attrs.get("type") or "").lower()

    def sanitize_value(name: str, value: str) -> str:
        if name == "style":
            return _sanitize_css(value, asset_root=asset_root, base_url=base_url, blocked=blocked)
        if name == "srcset":
            return _sanitize_srcset(value, asset_root=asset_root, base_url=base_url, blocked=blocked)
        if name in _URL_ATTRIBUTES:
            return _resource_url(
                value,
                asset_root=asset_root,
                base_url=base_url,
                blocked=blocked,
                context=f"{event.tag}.{name}",
            )
        return value

    raw = _EVENT_ATTRIBUTE_RE.sub("", event.raw)
    raw = _MARKER_ATTRIBUTE_RE.sub("", raw)

    def replace_attribute(match: re.Match[str]) -> str:
        name = match.group("name").lower()
        value = match.group("value")
        if blocked_script and name == "type":
            return ""
        value = sanitize_value(name, value)
        return f"{match.group('space')}{match.group('name')}{match.group('equals')}{match.group('quote')}{_quoted_attribute_value(value)}{match.group('quote')}"

    raw = _ATTRIBUTE_RE.sub(replace_attribute, raw)
    def replace_unquoted_attribute(match: re.Match[str]) -> str:
        name = match.group("name").lower()
        if blocked_script and name == "type":
            return ""
        if name not in _URL_ATTRIBUTES and name not in {"srcset", "style"}:
            return match.group(0)
        value = sanitize_value(name, match.group("value"))
        return f'{match.group("space")}{match.group("name")}{match.group("equals")}"{_quoted_attribute_value(value)}"'

    raw = _UNQUOTED_ATTRIBUTE_RE.sub(replace_unquoted_attribute, raw)
    if blocked_script:
        # JSON chart specs remain inert data; every other candidate script is
        # made inert before the document reaches the sandbox.
        closing = "/>" if raw.rstrip().endswith("/>") else ">"
        raw = raw.rstrip()[: -len(closing)] + ' type="application/workbench-blocked"' + closing
    return raw


def _insert_marker(raw: str, marker: str) -> str:
    closing = "/>" if raw.rstrip().endswith("/>") else ">"
    index = raw.rfind(closing)
    if index < 0:
        return raw
    return f'{raw[:index]} data-workbench-marker="{marker}"{raw[index:]}'


def _injected_script(nonce: str) -> str:
    # Keep this script self-contained: it is the only executable code allowed
    # in the Preview frame, and it communicates through postMessage only.
    return f"""<script nonce=\"{nonce}\">
(() => {{
  const channel = "officecli-workbench-preview";
  const send = (type, data) => window.parent.postMessage(Object.assign({{channel, type}}, data || {{}}), "*");
  const slides = Array.from(document.querySelectorAll(".slide"));
  const svgElement = (name, attributes) => {{
    const element = document.createElementNS("http://www.w3.org/2000/svg", name);
    Object.entries(attributes || {{}}).forEach(([key, value]) => element.setAttribute(key, String(value)));
    return element;
  }};
  const renderColumnChartProjection = (chart) => {{
    const specNode = chart.querySelector("script[data-pptx-chart-spec]");
    if (!specNode) return;
    let spec;
    try {{
      spec = JSON.parse(specNode.textContent || "");
    }} catch (_) {{
      return;
    }}
    if (!spec || spec.type !== "column" || !Array.isArray(spec.categories) || !Array.isArray(spec.series) || !spec.series.length) return;
    const series = spec.series[0];
    if (!series || !Array.isArray(series.values) || series.values.length !== spec.categories.length) return;
    const values = series.values.map((value) => Number(value));
    if (values.some((value) => !Number.isFinite(value) || value < 0)) return;
    const width = parseFloat(getComputedStyle(chart).width) || 760;
    const height = parseFloat(getComputedStyle(chart).height) || 480;
    const plot = {{left: 72, top: 42, right: width - 26, bottom: height - 58}};
    const plotWidth = Math.max(1, plot.right - plot.left);
    const plotHeight = Math.max(1, plot.bottom - plot.top);
    const maximum = Math.max(1, ...values);
    const axisMax = Math.max(1, Math.ceil(maximum * 2) / 2 + 0.5);
    const step = 0.5;
    const color = /^#[0-9a-f]{{6}}$/i.test(String(series.color || "")) ? String(series.color) : "#1D4ED8";
    const oldProjection = chart.querySelector(".workbench-chart-projection");
    if (oldProjection) oldProjection.remove();
    chart.querySelectorAll(":scope > [aria-hidden='true']").forEach((node) => node.remove());

    const svg = svgElement("svg", {{
      class: "workbench-chart-projection",
      "aria-label": String((spec.presentation && spec.presentation.title) || "Chart"),
      role: "img",
      viewBox: `0 0 ${{width}} ${{height}}`,
      preserveAspectRatio: "none",
    }});
    svg.style.cssText = "display:block;width:100%;height:100%;pointer-events:none";
    const title = svgElement("text", {{x: width / 2, y: 20, "text-anchor": "middle", fill: "#0f172a", "font-family": "Segoe UI, Microsoft YaHei, sans-serif", "font-size": 16, "font-weight": 700}});
    title.textContent = String((spec.presentation && spec.presentation.title) || "");
    svg.appendChild(title);
    for (let tick = 0; tick <= axisMax + 0.001; tick += step) {{
      const y = plot.bottom - (tick / axisMax) * plotHeight;
      svg.appendChild(svgElement("line", {{x1: plot.left, y1: y, x2: plot.right, y2: y, stroke: "#e2e8f0", "stroke-width": 1}}));
      const tickLabel = svgElement("text", {{x: plot.left - 9, y: y + 4, "text-anchor": "end", fill: "#475569", "font-family": "Segoe UI, Microsoft YaHei, sans-serif", "font-size": 10}});
      tickLabel.textContent = Number.isInteger(tick) ? String(tick) : tick.toFixed(1);
      svg.appendChild(tickLabel);
    }}
    svg.appendChild(svgElement("line", {{x1: plot.left, y1: plot.top, x2: plot.left, y2: plot.bottom, stroke: "#94a3b8", "stroke-width": 1}}));
    svg.appendChild(svgElement("line", {{x1: plot.left, y1: plot.bottom, x2: plot.right, y2: plot.bottom, stroke: "#94a3b8", "stroke-width": 1}}));
    const groupWidth = plotWidth / spec.categories.length;
    values.forEach((value, index) => {{
      const barWidth = groupWidth * 0.48;
      const x = plot.left + groupWidth * index + (groupWidth - barWidth) / 2;
      const barHeight = (value / axisMax) * plotHeight;
      const y = plot.bottom - barHeight;
      svg.appendChild(svgElement("rect", {{x, y, width: barWidth, height: barHeight, fill: color}}));
      const valueLabel = svgElement("text", {{x: x + barWidth / 2, y: Math.max(plot.top + 10, y - 5), "text-anchor": "middle", fill: "#334155", "font-family": "Segoe UI, Microsoft YaHei, sans-serif", "font-size": 10}});
      valueLabel.textContent = String(value);
      svg.appendChild(valueLabel);
      const categoryLabel = svgElement("text", {{x: x + barWidth / 2, y: plot.bottom + 20, "text-anchor": "middle", fill: "#334155", "font-family": "Segoe UI, Microsoft YaHei, sans-serif", "font-size": 10}});
      categoryLabel.textContent = String(spec.categories[index]);
      svg.appendChild(categoryLabel);
    }});
    chart.insertBefore(svg, specNode);
  }};
  const renderChartProjections = () => document.querySelectorAll("[data-pptx-chart]").forEach(renderColumnChartProjection);
  const initial = Math.max(0, slides.findIndex((slide) => slide.classList.contains("active")));
  slides.forEach((slide) => {{
    slide.dataset.workbenchOriginalDisplay = getComputedStyle(slide).display;
  }});
  const activate = (index) => {{
    const selected = Math.max(0, Math.min(Number(index) || 0, slides.length - 1));
    slides.forEach((slide, i) => {{
      slide.style.display = i === selected ? (slide.dataset.workbenchOriginalDisplay === "none" ? "block" : slide.dataset.workbenchOriginalDisplay) : "none";
      slide.dataset.workbenchSlideState = i === selected ? "current" : "hidden";
    }});
    send("slide", {{index: selected + 1}});
  }};
  const fit = () => {{
    const slide = slides[0];
    if (!slide) return;
    const width = parseFloat(getComputedStyle(slide).width) || 1920;
    const height = parseFloat(getComputedStyle(slide).height) || 1080;
    const scale = Math.min(window.innerWidth / width, window.innerHeight / height);
    document.documentElement.style.width = width + "px";
    document.documentElement.style.height = height + "px";
    document.body.style.width = width + "px";
    document.body.style.height = height + "px";
    document.body.style.transformOrigin = "0 0";
    document.body.style.transform = `scale(${{Math.max(0.01, scale)}})`;
  }};
  document.addEventListener("click", (event) => {{
    const target = event.target && event.target.closest ? event.target.closest("[data-workbench-marker]") : null;
    if (!target) return;
    send("selection", {{marker: target.getAttribute("data-workbench-marker"), slide: Number(target.closest(".slide")?.dataset.workbenchSlide || 0)}});
  }});
  window.addEventListener("message", (event) => {{
    if (event.source !== window.parent || !event.data || event.data.channel !== channel || event.data.type !== "show-slide") return;
    activate(event.data.index);
  }});
  slides.forEach((slide, index) => {{ slide.dataset.workbenchSlide = String(index + 1); }});
  renderChartProjections();
  fit();
  window.addEventListener("resize", fit);
  activate(initial);
  send("ready", {{slideCount: slides.length, currentSlide: initial + 1}});
}})();
</script>"""


def build_preview(
    text: str,
    *,
    asset_root: Path,
    resource_base_url: str,
    preview_origin: str,
) -> PreviewProduct:
    """Instrument one draft in memory and return the isolated Preview product."""
    parser = _SourceParser(text)
    try:
        parser.feed(text)
        parser.close()
    except Exception:
        parser.repaired = True
    parser.finish()

    blocked_resources: list[dict[str, str]] = []
    replacements: list[tuple[int, int, str]] = []
    source_map: dict[str, dict[str, Any]] = {}
    marker_count = 0
    for event in parser.events:
        sanitized = _sanitize_start_tag(
            event,
            asset_root=asset_root,
            base_url=resource_base_url,
            blocked=blocked_resources,
        )
        kind = _kind_for(event)
        if event.tag == "base":
            replacements.append((event.start, event.end, "<!-- workbench blocked candidate base -->"))
            continue
        if event.tag == "meta" and (event.attrs.get("http-equiv") or "").lower() == "refresh":
            replacements.append((event.start, event.end, "<!-- workbench blocked candidate refresh -->"))
            continue
        if kind is None:
            if sanitized != event.raw:
                replacements.append((event.start, event.end, sanitized))
            continue
        marker = f"wb-{marker_count}"
        marker_count += 1
        status = "unmapped" if parser.repaired else "mapped"
        reason = "parser_repaired_candidate" if parser.repaired else None
        # ``HTMLParser.getpos`` points at the most recent callback, so derive
        # the stable source line/column from the collected character offset.
        line_number = text.count("\n", 0, event.start) + 1
        last_newline = text.rfind("\n", 0, event.start)
        column_number = event.start if last_newline < 0 else event.start - last_newline - 1
        entry = PreviewMapEntry(
            marker=marker,
            kind=kind,
            tag=event.tag,
            slide=event.slide,
            source_start=None if parser.repaired else event.start,
            source_end=None if parser.repaired else event.end,
            editor_start=None if parser.repaired else _editor_offset(text[:event.start]),
            editor_end=None if parser.repaired else _editor_offset(text[:event.end]),
            line=None if parser.repaired else line_number,
            column=None if parser.repaired else column_number,
            status=status,
            reason=reason,
        ).as_dict()
        source_map[marker] = entry
        replacements.append((event.start, event.end, _insert_marker(sanitized, marker)))

    for start, end in parser.style_data:
        value = _sanitize_css(
            text[start:end],
            asset_root=asset_root,
            base_url=resource_base_url,
            blocked=blocked_resources,
        )
        if value != text[start:end]:
            replacements.append((start, end, value))

    nonce = quote(f"preview-{marker_count}-{len(text)}", safe="")
    csp = (
        "default-src 'none'; "
        "base-uri 'none'; "
        f"style-src 'unsafe-inline' {preview_origin}; "
        f"img-src data: blob: {preview_origin}; "
        f"font-src data: {preview_origin}; "
        f"media-src data: {preview_origin}; "
        f"script-src 'nonce-{nonce}'; connect-src 'none'; "
        "frame-src 'none'; child-src 'none'; object-src 'none'; form-action 'none'; "
        "navigate-to 'none'"
    )
    prefix = (
        '<meta name="workbench-preview" content="16:9">'
        f'<meta http-equiv="Content-Security-Policy" content="{escape(csp, quote=True)}">'
        '<style data-workbench-style="ephemeral">html,body{margin:0;overflow:hidden;}</style>'
    )
    script = _injected_script(nonce)
    insertions: dict[int, list[str]] = {}
    if parser.head_end is not None:
        insertions.setdefault(parser.head_end, []).append(prefix)
    else:
        insertions.setdefault(0, []).append(prefix)
    if parser.body_end is not None:
        insertions.setdefault(parser.body_end, []).append(script)
    else:
        insertions.setdefault(len(text), []).append(script)

    pieces: list[str] = []
    replacement_by_start = {start: (end, value) for start, end, value in replacements}
    index = 0
    while index < len(text):
        if index in insertions:
            pieces.extend(insertions[index])
        replacement = replacement_by_start.get(index)
        if replacement is not None:
            end, value = replacement
            pieces.append(value)
            index = end
            continue
        pieces.append(text[index])
        index += 1
    if len(text) in insertions:
        pieces.extend(insertions[len(text)])
    rendered = "".join(pieces)

    slides: list[dict[str, Any]] = []
    for index in range(parser.slide_count):
        slides.append({"index": index + 1, "label": f"Slide {index + 1}", "thumbnail": "ephemeral"})
    return PreviewProduct(
        html=rendered,
        source_map=source_map,
        slide_count=parser.slide_count,
        slides=tuple(slides),
        blocked_resources=tuple(blocked_resources),
        parser_repaired=parser.repaired,
    )


def resource_content_type(path: Path) -> str:
    if path.suffix.lower() not in _LOCAL_RESOURCE_SUFFIXES:
        return "application/octet-stream"
    content_type, _ = mimetypes.guess_type(path.name)
    return content_type or "application/octet-stream"


__all__ = ["PreviewProduct", "build_preview", "resource_content_type"]
