from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import quote


DEFAULT_ICON_DATA_URI = (
	"data:image/svg+xml;charset=UTF-8,"
	+ quote(
		"""
		<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'>
			<defs>
				<linearGradient id='g' x1='0%' y1='0%' x2='100%' y2='100%'>
					<stop offset='0%' stop-color='#6de2d5'/>
					<stop offset='100%' stop-color='#9db7ff'/>
				</linearGradient>
			</defs>
			<rect x='6' y='6' width='52' height='52' rx='16' fill='url(#g)'/>
			<circle cx='24' cy='24' r='6' fill='#08111f'/>
			<path d='M18 39c4-7 8-10 14-10s10 3 14 10' fill='none' stroke='#08111f' stroke-width='5' stroke-linecap='round'/>
		</svg>
		""".strip()
	)
)


@dataclass
class Bookmark:
	title: str
	href: str
	icon: str = ""
	add_date: str = ""


@dataclass
class Folder:
	title: str
	children: list[Any] = field(default_factory=list)


class BookmarksParser(HTMLParser):
	def __init__(self) -> None:
		super().__init__(convert_charrefs=True)
		self.root = Folder(title="收藏夹")
		self.stack: list[Folder] = [self.root]
		self.pending_folder: Folder | None = None
		self.collecting: str | None = None
		self.buffer: list[str] = []
		self.current_attrs: dict[str, str] = {}

	def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
		tag = tag.lower()
		if tag == "h3":
			self.collecting = "folder"
			self.buffer = []
			self.current_attrs = {k.lower(): v or "" for k, v in attrs}
		elif tag == "a":
			self.collecting = "bookmark"
			self.buffer = []
			self.current_attrs = {k.lower(): v or "" for k, v in attrs}
		elif tag == "dl":
			if self.pending_folder is not None:
				self.stack.append(self.pending_folder)
				self.pending_folder = None

	def handle_endtag(self, tag: str) -> None:
		tag = tag.lower()
		if tag == "h3" and self.collecting == "folder":
			title = "".join(self.buffer).strip() or "未命名文件夹"
			folder = Folder(title=title)
			self.stack[-1].children.append(folder)
			self.pending_folder = folder
			self.collecting = None
			self.buffer = []
			self.current_attrs = {}
		elif tag == "a" and self.collecting == "bookmark":
			title = "".join(self.buffer).strip() or "未命名链接"
			bookmark = Bookmark(
				title=title,
				href=self.current_attrs.get("href", ""),
				icon=self.current_attrs.get("icon", ""),
				add_date=self.current_attrs.get("add_date", ""),
			)
			self.stack[-1].children.append(bookmark)
			self.collecting = None
			self.buffer = []
			self.current_attrs = {}
		elif tag == "dl":
			if len(self.stack) > 1:
				self.stack.pop()

	def handle_data(self, data: str) -> None:
		if self.collecting:
			self.buffer.append(data)


def parse_bookmarks(path: Path) -> Folder:
	parser = BookmarksParser()
	parser.feed(path.read_text(encoding="utf-8"))
	parser.close()
	return parser.root


def iter_nodes(folder: Folder):
	for child in folder.children:
		yield child
		if isinstance(child, Folder):
			yield from iter_nodes(child)


def count_stats(root: Folder) -> tuple[int, int]:
	folders = 0
	bookmarks = 0
	for node in iter_nodes(root):
		if isinstance(node, Folder):
			folders += 1
		else:
			bookmarks += 1
	return folders, bookmarks


def extract_domains(root: Folder, limit: int = 8) -> list[tuple[str, int]]:
	counter: Counter[str] = Counter()
	for node in iter_nodes(root):
		if isinstance(node, Bookmark) and node.href:
			host = node.href.split("//", 1)[-1].split("/", 1)[0].lower()
			if host.startswith("www."):
				host = host[4:]
			if host:
				counter[host] += 1
	return counter.most_common(limit)


def safe_id(text: str, index: int | str) -> str:
	cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in text)
	cleaned = "-".join(part for part in cleaned.split("-") if part)
	return cleaned or f"section-{index}"


def folder_anchor(folder: Folder, path: tuple[int, ...]) -> str:
	path_suffix = "-".join(str(part) for part in path) or "root"
	return safe_id(f"{folder.title}-{path_suffix}", path_suffix)


def split_folder_children(folder: Folder) -> tuple[list[Bookmark], list[Folder]]:
	bookmark_nodes: list[Bookmark] = []
	folder_nodes: list[Folder] = []
	for child in folder.children:
		if isinstance(child, Bookmark):
			bookmark_nodes.append(child)
		elif isinstance(child, Folder):
			folder_nodes.append(child)
	return bookmark_nodes, folder_nodes


def favicon_url(bookmark: Bookmark) -> str:
	if bookmark.icon:
		return bookmark.icon
	if not bookmark.href:
		return DEFAULT_ICON_DATA_URI
	return f"https://www.google.com/s2/favicons?sz=64&domain_url={bookmark.href}"


def render_bookmark(bookmark: Bookmark) -> str:
	icon_src = favicon_url(bookmark)
	domain = bookmark.href.split("//", 1)[-1].split("/", 1)[0].lower() if bookmark.href else ""
	label = domain[4:] if domain.startswith("www.") else domain
	return f"""
		<a class="bookmark-card" href="{escape(bookmark.href, quote=True)}" target="_blank" rel="noopener noreferrer" data-search="{escape((bookmark.title + ' ' + bookmark.href + ' ' + label), quote=True)}">
			<span class="bookmark-icon">
				<img class="bookmark-favicon" src="{escape(icon_src, quote=True)}" alt="" loading="lazy" decoding="async">
			</span>
			<span class="bookmark-body">
				<span class="bookmark-title">{escape(bookmark.title)}</span>
				<span class="bookmark-meta">{escape(label or 'direct link')}</span>
			</span>
		</a>
	"""


def render_folder_nav(folder: Folder, path: tuple[int, ...] = (), level: int = 0) -> str:
	bookmark_nodes, folder_nodes = split_folder_children(folder)
	if not folder_nodes:
		return ""
	items: list[str] = []
	for child_index, child in enumerate(folder_nodes):
		child_path = path + (child_index,)
		child_id = folder_anchor(child, child_path)
		child_nav = render_folder_nav(child, child_path, level + 1)
		toggle_button = ""
		children_html = ""
		if child_nav:
			toggle_button = f"""
				<button class="nav-fold-toggle" type="button" aria-expanded="true" aria-label="折叠 {escape(child.title)}" data-folder-title="{escape(child.title, quote=True)}">
					<span aria-hidden="true">▾</span>
				</button>
			"""
			children_html = f'<div class="nav-children">{child_nav}</div>'
		items.append(
			f"""
			<div class="nav-item level-{level + 1}" data-nav-id="{child_id}" data-collapsed="false">
				<div class="nav-row">
					{toggle_button}
					<a class="nav-link" href="#{child_id}">
						<span>{escape(child.title)}</span>
						<em>{sum(isinstance(node, Bookmark) for node in child.children)} 个链接</em>
					</a>
				</div>
				{children_html}
			</div>
			"""
		)
	return f"<div class=\"nav-tree\">{''.join(items)}</div>"


def render_sidebar(root: Folder) -> str:
	return f"""
		<div class="sidebar-card">
			<button id="sidebarToggle" class="sidebar-toggle" type="button" aria-expanded="true" aria-label="折叠侧边导航栏">
				<span class="sidebar-toggle-icon">⟨</span>
				<span class="sidebar-toggle-text">收起</span>
			</button>
			<div class="sidebar-main">
				<p class="sidebar-kicker">文件夹导航</p>
				<h2>快速跳转</h2>
				<p class="sidebar-note">点击左侧文件夹，直接定位到对应收藏分组。</p>
				<a class="sidebar-home" href="#content">回到顶部收藏</a>
				{render_folder_nav(root)}
			</div>
		</div>
	"""


def render_folder(folder: Folder, level: int = 0, path: tuple[int, ...] = ()) -> tuple[str, int]:
	folder_id = folder_anchor(folder, path)
	bookmark_nodes, folder_nodes = split_folder_children(folder)
	html_parts: list[str] = []

	if level > 0 or folder.title != "收藏夹":
		html_parts.append(
			f"""
			<section class="folder-card level-{level}" id="{folder_id}" data-search="{escape(folder.title, quote=True)}">
				<div class="folder-head">
					<div>
						<p class="folder-kicker">收藏分组</p>
						<h2>{escape(folder.title)}</h2>
						<p class="folder-count">{len(bookmark_nodes)} 个链接 · {len(folder_nodes)} 个子分组</p>
					</div>
					<button class="folder-toggle" type="button" aria-expanded="true">收起</button>
				</div>
				<div class="folder-body">
			"""
		)

	if bookmark_nodes:
		html_parts.append('<div class="bookmark-grid">')
		for bookmark in bookmark_nodes:
			html_parts.append(render_bookmark(bookmark))
		html_parts.append('</div>')

	for child_index, child in enumerate(folder_nodes):
		child_html, _ = render_folder(child, level + 1, path + (child_index,))
		html_parts.append(child_html)

	if level > 0 or folder.title != "收藏夹":
		html_parts.append('</div></section>')

	return "".join(html_parts), 0


def render_feature_tags(domains: list[tuple[str, int]]) -> str:
	if not domains:
		return ""
	chips = "".join(
		f'<span class="chip"><strong>{escape(name)}</strong><em>{count}</em></span>'
		for name, count in domains
	)
	return f"<div class=\"chip-row\">{chips}</div>"


def build_html(root: Folder, source_name: str) -> str:
	folders, bookmarks = count_stats(root)
	domains = extract_domains(root)
	content_html, _ = render_folder(root)
	total_nodes = bookmarks + folders
	title = f"{root.title} · 导航站"
	return f"""<!doctype html>
<html lang="zh-CN">
<head>
	<meta charset="utf-8">
	<meta name="viewport" content="width=device-width, initial-scale=1">
	<meta name="color-scheme" content="dark light">
	<title>{escape(title)}</title>
	<style>
		:root {{
			--bg: #08111f;
			--bg-2: #0d1a2c;
			--card: rgba(10, 18, 33, 0.56);
			--card-strong: rgba(17, 27, 47, 0.82);
			--line: rgba(255, 255, 255, 0.08);
			--text: #ecf2ff;
			--muted: rgba(236, 242, 255, 0.72);
			--accent: #6de2d5;
			--accent-2: #9db7ff;
			--accent-3: #f1c27d;
			--shadow: 0 24px 80px rgba(0, 0, 0, 0.35);
		}}
		* {{ box-sizing: border-box; }}
		html {{ scroll-behavior: smooth; }}
		body {{
			margin: 0;
			color: var(--text);
			background:
				radial-gradient(circle at top left, rgba(109, 226, 213, 0.18), transparent 26%),
				radial-gradient(circle at top right, rgba(157, 183, 255, 0.16), transparent 24%),
				radial-gradient(circle at bottom left, rgba(241, 194, 125, 0.12), transparent 24%),
				linear-gradient(135deg, var(--bg), var(--bg-2));
			font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
			min-height: 100vh;
		}}
		body::before {{
			content: "";
			position: fixed;
			inset: 0;
			pointer-events: none;
			background-image: linear-gradient(rgba(255, 255, 255, 0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(255, 255, 255, 0.03) 1px, transparent 1px);
			background-size: 72px 72px;
			mask-image: linear-gradient(to bottom, rgba(0, 0, 0, 0.28), transparent 72%);
			opacity: 0.5;
		}}
		a {{ color: inherit; text-decoration: none; }}
		.shell {{ max-width: 1460px; margin: 0 auto; padding: 28px 20px 60px; position: relative; z-index: 1; }}
		.hero {{
			position: relative;
			overflow: hidden;
			border: 1px solid var(--line);
			border-radius: 28px;
			background: linear-gradient(180deg, rgba(19, 31, 54, 0.8), rgba(11, 18, 33, 0.6));
			box-shadow: var(--shadow);
			backdrop-filter: blur(18px);
			padding: 28px;
		}}
		.hero::after {{
			content: "";
			position: absolute;
			inset: auto -120px -160px auto;
			width: 320px;
			height: 320px;
			border-radius: 50%;
			background: radial-gradient(circle, rgba(109, 226, 213, 0.22), transparent 68%);
			filter: blur(12px);
		}}
		.eyebrow {{
			display: inline-flex;
			align-items: center;
			gap: 10px;
			padding: 8px 14px;
			border-radius: 999px;
			background: rgba(255, 255, 255, 0.06);
			border: 1px solid var(--line);
			color: var(--muted);
			font-size: 13px;
			letter-spacing: 0.04em;
			text-transform: uppercase;
		}}
		.hero h1 {{ margin: 18px 0 8px; font-size: clamp(30px, 4vw, 56px); line-height: 1.04; }}
		.hero p {{ margin: 0; color: var(--muted); max-width: 72ch; line-height: 1.8; }}
		.web-search {{
			margin-top: 22px;
			display: grid;
			grid-template-columns: minmax(0, 1.4fr) 220px auto;
			gap: 12px;
			padding: 16px;
			border: 1px solid rgba(109, 226, 213, 0.18);
			background: linear-gradient(135deg, rgba(255, 255, 255, 0.06), rgba(109, 226, 213, 0.08));
			backdrop-filter: blur(16px);
			border-radius: 24px;
			box-shadow: var(--shadow);
			position: relative;
			z-index: 10;
		}}
		.web-search-field, .web-search-select, .web-search-submit {{
			display: flex;
			align-items: center;
			gap: 12px;
			min-width: 0;
			border: 1px solid rgba(255, 255, 255, 0.08);
			background: rgba(7, 14, 26, 0.48);
			border-radius: 18px;
			padding: 14px 16px;
		}}
		.web-search-field input, .web-search-select select {{
			width: 100%;
			border: 0;
			outline: 0;
			background: transparent;
			color: var(--text);
			font-size: 15px;
			min-width: 0;
		}}
		.web-search-field input::placeholder {{ color: rgba(236, 242, 255, 0.48); }}
		.web-search-select {{
			position: relative;
			justify-content: space-between;
			padding-right: 42px;
			cursor: pointer;
			background: rgba(7, 14, 26, 0.48) !important;
			border: 1px solid rgba(255, 255, 255, 0.08) !important;
			z-index: 20;
		}}
		.web-search-select::after {{
			content: "▾";
			position: absolute;
			right: 16px;
			top: 50%;
			transform: translateY(-50%);
			color: var(--accent);
			font-size: 12px;
			pointer-events: none;
			transition: transform 160ms ease;
		}}
		.web-search-select[data-open="true"]::after {{
			transform: translateY(-50%) rotate(180deg);
		}}
		.web-search-select:focus-within {{
			border-color: rgba(109, 226, 213, 0.42) !important;
			background: rgba(15, 24, 41, 0.78) !important;
			box-shadow: 0 0 0 3px rgba(109, 226, 213, 0.1);
		}}
		.web-search-select:hover {{
			border-color: rgba(109, 226, 213, 0.28) !important;
			background: rgba(15, 24, 41, 0.68) !important;
		}}
		.web-search-select span {{ color: var(--muted); font-size: 13px; flex: 0 0 auto; }}
		.web-search-select select {{ appearance: none; cursor: pointer; padding-right: 8px; flex: 1; opacity: 0; width: 100%; pointer-events: none; }}
		.search-engine-dropdown {{
			position: fixed;
			background: rgba(8, 17, 31, 0.95);
			border: 1px solid rgba(109, 226, 213, 0.28);
			border-radius: 16px;
			box-shadow: 0 12px 48px rgba(0, 0, 0, 0.48);
			backdrop-filter: blur(18px);
			min-width: 180px;
			display: none;
			z-index: 10000;
			overflow: hidden;
			max-height: 320px;
			overflow-y: auto;
		}}
		.search-engine-dropdown[data-visible="true"] {{
			display: grid;
		}}
		.search-engine-item {{
			padding: 12px 16px;
			cursor: pointer;
			display: flex;
			align-items: center;
			gap: 12px;
			border: none;
			background: transparent;
			color: var(--text);
			width: 100%;
			text-align: left;
			font-size: 14px;
			transition: background 120ms ease, color 120ms ease;
			border-left: 3px solid transparent;
		}}
		.search-engine-item:hover {{
			background: rgba(109, 226, 213, 0.12);
			color: var(--accent);
		}}
		.search-engine-item[data-selected="true"] {{
			background: rgba(109, 226, 213, 0.18);
			color: var(--accent);
			border-left-color: var(--accent);
		}}
		.search-engine-item::before {{
			content: "";
			display: inline-block;
			width: 8px;
			height: 8px;
			border-radius: 50%;
			background: currentColor;
			opacity: 0.6;
		}}
		.search-engine-item[data-selected="true"]::before {{
			background: var(--accent);
			opacity: 1;
			width: 10px;
			height: 10px;
		}}
		.web-search-submit {{
			justify-content: center;
			border: 1px solid rgba(109, 226, 213, 0.24);
			background: linear-gradient(135deg, rgba(109, 226, 213, 0.18), rgba(157, 183, 255, 0.16));
			color: var(--text);
			font-weight: 600;
			cursor: pointer;
			transition: transform 160ms ease, border-color 160ms ease, background 160ms ease;
			box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08);
		}}
		.web-search-submit:hover {{ transform: translateY(-1px); border-color: rgba(109, 226, 213, 0.42); background: linear-gradient(135deg, rgba(109, 226, 213, 0.24), rgba(157, 183, 255, 0.22)); }}
		.toolbar {{
			margin-top: 22px;
			display: grid;
			grid-template-columns: minmax(0, 1.4fr) repeat(3, minmax(0, 0.5fr));
			gap: 14px;
		}}
		.search, .stat {{
			border: 1px solid var(--line);
			background: var(--card);
			backdrop-filter: blur(16px);
			border-radius: 22px;
			box-shadow: var(--shadow);
		}}
		.search {{ padding: 16px 18px; display: flex; align-items: center; gap: 12px; }}
		.search input {{
			width: 100%;
			border: 0;
			outline: 0;
			background: transparent;
			color: var(--text);
			font-size: 16px;
		}}
		.search input::placeholder {{ color: rgba(236, 242, 255, 0.45); }}
		.stat {{ padding: 16px 18px; display: grid; gap: 4px; align-content: center; }}
		.stat span {{ color: var(--muted); font-size: 12px; }}
		.stat strong {{ font-size: 24px; line-height: 1; }}
		.chip-row {{ margin-top: 16px; display: flex; flex-wrap: wrap; gap: 10px; }}
		.chip {{
			display: inline-flex;
			gap: 10px;
			align-items: center;
			padding: 10px 14px;
			border-radius: 999px;
			border: 1px solid var(--line);
			background: rgba(255, 255, 255, 0.05);
			backdrop-filter: blur(12px);
		}}
		.chip strong {{ font-size: 14px; }}
		.chip em {{ font-style: normal; color: var(--muted); }}
		.layout {{ --sidebar-width: 320px; margin-top: 24px; display: grid; grid-template-columns: var(--sidebar-width) minmax(0, 1fr); gap: 18px; align-items: start; }}
		.layout[data-sidebar-collapsed="true"] {{ --sidebar-width: 88px; }}
		.sidebar {{ position: sticky; top: 24px; align-self: start; }}
		.sidebar-card {{
			border: 1px solid var(--line);
			border-radius: 24px;
			background: rgba(8, 17, 31, 0.78);
			backdrop-filter: blur(18px);
			box-shadow: var(--shadow);
			padding: 20px;
			max-height: calc(100vh - 48px);
			overflow: auto;
			scrollbar-width: thin;
			scrollbar-color: rgba(109, 226, 213, 0.55) rgba(255, 255, 255, 0.06);
		}}
		.sidebar-card::-webkit-scrollbar {{ width: 10px; }}
		.sidebar-card::-webkit-scrollbar-track {{ background: rgba(255, 255, 255, 0.04); border-radius: 999px; }}
		.sidebar-card::-webkit-scrollbar-thumb {{
			background: linear-gradient(180deg, rgba(109, 226, 213, 0.8), rgba(157, 183, 255, 0.8));
			border-radius: 999px;
			border: 2px solid rgba(8, 17, 31, 0.78);
		}}
		.sidebar-card::-webkit-scrollbar-thumb:hover {{
			background: linear-gradient(180deg, rgba(109, 226, 213, 1), rgba(157, 183, 255, 1));
		}}
		.sidebar-toggle {{
			display: inline-flex;
			align-items: center;
			justify-content: center;
			gap: 8px;
			width: 100%;
			padding: 10px 14px;
			border: 1px solid rgba(109, 226, 213, 0.22);
			border-radius: 16px;
			background: linear-gradient(135deg, rgba(109, 226, 213, 0.12), rgba(157, 183, 255, 0.1));
			color: var(--text);
			cursor: pointer;
			box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08);
		}}
		.sidebar-toggle:hover {{ border-color: rgba(109, 226, 213, 0.4); background: linear-gradient(135deg, rgba(109, 226, 213, 0.18), rgba(157, 183, 255, 0.16)); }}
		.sidebar-toggle-icon {{ font-size: 14px; line-height: 1; }}
		.sidebar-toggle-text {{ font-size: 13px; letter-spacing: 0.04em; }}
		.sidebar-main {{ display: grid; gap: 0; margin-top: 18px; }}
		.layout[data-sidebar-collapsed="true"] .sidebar-card {{ padding: 14px 10px; }}
		.layout[data-sidebar-collapsed="true"] .sidebar-main {{ display: none; }}
		.layout[data-sidebar-collapsed="true"] .sidebar-toggle {{ padding: 12px 10px; border-radius: 18px; }}
		.layout[data-sidebar-collapsed="true"] .sidebar-toggle-text {{ display: none; }}
		.layout[data-sidebar-collapsed="true"] .sidebar-toggle-icon {{ transform: rotate(180deg); }}
		.sidebar-kicker {{ margin: 0 0 6px; color: var(--accent); font-size: 12px; letter-spacing: 0.16em; text-transform: uppercase; }}
		.sidebar-card h2 {{ margin: 0; font-size: 22px; }}
		.sidebar-note {{ margin-top: 10px; color: var(--muted); line-height: 1.7; font-size: 14px; }}
		.sidebar-home {{
			display: inline-flex;
			margin-top: 16px;
			padding: 10px 14px;
			border-radius: 999px;
			border: 1px solid var(--line);
			background: rgba(255, 255, 255, 0.05);
			font-size: 13px;
		}}
		.nav-list {{ list-style: none; padding: 14px 0 0; margin: 0; display: grid; gap: 10px; }}
		.nav-list-nested {{ padding-left: 16px; border-left: 1px solid rgba(255, 255, 255, 0.08); }}
		.nav-item {{ display: grid; gap: 10px; }}
		.nav-row {{ display: flex; align-items: stretch; gap: 10px; min-width: 0; }}
		.nav-fold-toggle {{
			width: 34px;
			min-width: 34px;
			height: 34px;
			border: 1px solid rgba(255, 255, 255, 0.08);
			border-radius: 12px;
			background: rgba(255, 255, 255, 0.05);
			color: var(--text);
			cursor: pointer;
			display: inline-grid;
			place-items: center;
			padding: 0;
			flex: 0 0 auto;
			transition: background 160ms ease, border-color 160ms ease, transform 160ms ease;
		}}
		.nav-fold-toggle:hover {{ border-color: rgba(109, 226, 213, 0.34); background: rgba(15, 24, 41, 0.78); transform: translateY(-1px); }}
		.nav-fold-toggle span {{ display: inline-block; transition: transform 160ms ease; line-height: 1; }}
		.nav-link {{
			display: flex;
			justify-content: space-between;
			gap: 12px;
			align-items: center;
			padding: 12px 14px;
			border-radius: 16px;
			border: 1px solid transparent;
			background: rgba(255, 255, 255, 0.04);
			transition: background 160ms ease, border-color 160ms ease, transform 160ms ease;
		}}
		.nav-link span {{ min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
		.nav-link em {{ font-style: normal; color: var(--muted); font-size: 12px; flex: 0 0 auto; }}
		.nav-link:hover {{ border-color: rgba(109, 226, 213, 0.28); background: rgba(15, 24, 41, 0.82); transform: translateX(2px); }}
		.nav-children {{ margin-left: 17px; padding-left: 14px; border-left: 1px solid rgba(255, 255, 255, 0.08); display: grid; gap: 10px; }}
		.nav-item[data-collapsed="true"] > .nav-children {{ display: none; }}
		.nav-item[data-collapsed="true"] > .nav-row .nav-fold-toggle span {{ transform: rotate(-90deg); }}
		.nav-item[data-collapsed="true"] > .nav-row .nav-fold-toggle {{ border-color: rgba(109, 226, 213, 0.28); background: rgba(109, 226, 213, 0.12); color: var(--accent); }}
		.content {{ display: grid; gap: 18px; }}
		.folder-card {{
			border: 1px solid var(--line);
			border-radius: 24px;
			background: var(--card);
			backdrop-filter: blur(18px);
			box-shadow: var(--shadow);
			overflow: hidden;
		}}
		.folder-head {{
			display: flex;
			justify-content: space-between;
			gap: 18px;
			align-items: center;
			padding: 18px 20px;
			background: linear-gradient(180deg, rgba(255, 255, 255, 0.05), rgba(255, 255, 255, 0.01));
			border-bottom: 1px solid rgba(255, 255, 255, 0.06);
		}}
		.folder-kicker {{ margin: 0 0 4px; color: var(--accent); font-size: 12px; letter-spacing: 0.16em; text-transform: uppercase; }}
		.folder-head h2 {{ margin: 0; font-size: 22px; }}
		.folder-count {{ margin: 6px 0 0; color: var(--muted); font-size: 13px; }}
		.folder-toggle {{
			border: 0;
			padding: 10px 14px;
			border-radius: 999px;
			color: var(--text);
			background: rgba(255, 255, 255, 0.08);
			cursor: pointer;
		}}
		.folder-body {{ padding: 18px 20px 22px; }}
		.bookmark-grid {{
			display: grid;
			grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
			gap: 14px;
		}}
		.bookmark-card {{
			display: flex;
			gap: 12px;
			align-items: center;
			min-height: 82px;
			padding: 14px;
			border-radius: 18px;
			border: 1px solid rgba(255, 255, 255, 0.08);
			background: rgba(7, 14, 26, 0.48);
			transition: transform 160ms ease, border-color 160ms ease, background 160ms ease;
		}}
		.bookmark-card:hover {{ transform: translateY(-3px); border-color: rgba(109, 226, 213, 0.35); background: rgba(15, 24, 41, 0.78); }}
		.bookmark-icon {{
			width: 40px;
			height: 40px;
			border-radius: 12px;
			flex: 0 0 40px;
			overflow: hidden;
			display: grid;
			place-items: center;
			font-weight: 700;
			color: #08111f;
			background: linear-gradient(135deg, var(--accent), var(--accent-2));
			box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.45);
		}}
		.bookmark-favicon {{ width: 100%; height: 100%; display: block; object-fit: cover; }}
		.bookmark-favicon.is-default {{ padding: 7px; object-fit: contain; }}
		.bookmark-body {{ min-width: 0; display: grid; gap: 4px; }}
		.bookmark-title {{ font-size: 14px; line-height: 1.45; word-break: break-word; }}
		.bookmark-meta {{ color: var(--muted); font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
		.folder-card, .sidebar-card {{ scroll-margin-top: 24px; }}
		.folder-card[data-collapsed="true"] > .folder-body {{ display: none; }}
		.folder-card[data-collapsed="true"] > .folder-head .folder-toggle {{ background: rgba(109, 226, 213, 0.16); color: var(--accent); }}
		.folder-card.level-1 {{ background: var(--card-strong); }}
		.folder-card.level-2 {{ background: rgba(10, 18, 33, 0.68); }}
		.folder-card.level-3 {{ background: rgba(10, 18, 33, 0.76); }}
		.empty {{
			margin-top: 18px;
			padding: 28px;
			text-align: center;
			border: 1px dashed rgba(255, 255, 255, 0.14);
			border-radius: 22px;
			color: var(--muted);
		}}
		footer {{ margin-top: 24px; color: var(--muted); font-size: 13px; text-align: center; }}
		@media (max-width: 1100px) {{
			.toolbar {{ grid-template-columns: 1fr 1fr; }}
			.search {{ grid-column: 1 / -1; }}
			.layout {{ grid-template-columns: 1fr; }}
			.sidebar {{ position: static; }}
			.sidebar-card {{ max-height: none; }}
			.layout[data-sidebar-collapsed="true"] {{ --sidebar-width: 1fr; }}
			.layout[data-sidebar-collapsed="true"] .sidebar-card {{ padding: 16px; }}
			.layout[data-sidebar-collapsed="true"] .sidebar-main {{ display: grid; }}
			.layout[data-sidebar-collapsed="true"] .sidebar-toggle-text {{ display: inline; }}
			.layout[data-sidebar-collapsed="true"] .sidebar-toggle-icon {{ transform: none; }}
		}}
		@media (max-width: 700px) {{
			.shell {{ padding: 14px 12px 28px; }}
			.hero {{ padding: 20px; border-radius: 22px; }}
			.toolbar {{ grid-template-columns: 1fr; }}
			.folder-head {{ align-items: flex-start; flex-direction: column; }}
			.bookmark-grid {{ grid-template-columns: 1fr; }}
			.layout {{ margin-top: 18px; }}
			.sidebar-card {{ padding: 16px; }}
		}}
	</style>
</head>
<body>
	<main class="shell">
		<section class="hero">
			<div class="eyebrow">Edge Favorites Import · {escape(source_name)}</div>
			<h1>{escape(root.title)} 的简约导航站</h1>
			<p>把收藏夹整理成一个可直接打开的静态导航页，支持层级分组、快速搜索和毛玻璃视觉风格，方便日常检索与跳转。</p>
			<form class="web-search" id="webSearchForm">
				<label class="web-search-field" aria-label="网页搜索关键词">
					<span>⌕</span>
					<input id="webSearchInput" type="search" placeholder="搜索网页、资料或网站">
				</label>
				<div class="web-search-select" id="searchEngineSelector" data-open="false" aria-label="选择搜索引擎">
					<span>搜索引擎</span>
					<div id="selectedEngine">Bing</div>
					<select id="webSearchEngine" style="display: none;">
						<option value="bing" selected>Bing</option>
						<option value="google">Google</option>
						<option value="baidu">百度</option>
					</select>
					<div class="search-engine-dropdown" id="searchEngineDropdown" data-visible="false">
						<button type="button" class="search-engine-item" data-value="bing" data-selected="true" data-label="Bing">Bing</button>
						<button type="button" class="search-engine-item" data-value="google" data-label="Google">Google</button>
						<button type="button" class="search-engine-item" data-value="baidu" data-label="百度">百度</button>
					</div>
				</div>
				<button class="web-search-submit" type="submit">搜索网页</button>
			</form>
			<div class="toolbar">
				<label class="search" aria-label="搜索收藏">
					<span>⌕</span>
					<input id="searchInput" type="search" placeholder="搜索标题、网址或分组名称">
				</label>
				<div class="stat"><span>收藏总数</span><strong>{bookmarks}</strong></div>
				<div class="stat"><span>分组数量</span><strong>{folders}</strong></div>
				<div class="stat"><span>节点总数</span><strong>{total_nodes}</strong></div>
			</div>
			{render_feature_tags(domains)}
		</section>

		<section class="layout" data-sidebar-collapsed="false">
			<aside class="sidebar">
				{render_sidebar(root)}
			</aside>
			<section id="content" class="content">
				{content_html}
			</section>
		</section>

		<footer>生成于 {escape(source_name)} · 可直接双击打开，无需服务器</footer>
	</main>
	<script>
		const input = document.getElementById('searchInput');
		const webSearchForm = document.getElementById('webSearchForm');
		const webSearchInput = document.getElementById('webSearchInput');
		const webSearchEngine = document.getElementById('webSearchEngine');
		const searchEngineSelector = document.getElementById('searchEngineSelector');
		const selectedEngineDisplay = document.getElementById('selectedEngine');
		const searchEngineDropdown = document.getElementById('searchEngineDropdown');
		const searchEngineItems = Array.from(searchEngineDropdown.querySelectorAll('.search-engine-item'));
		const folders = Array.from(document.querySelectorAll('.folder-card'));
		const navItems = Array.from(document.querySelectorAll('.nav-item[data-nav-id]'));
		const layout = document.querySelector('.layout');
				const webSearchUrls = {{
					bing: 'https://www.bing.com/search?q=',
					google: 'https://www.google.com/search?q=',
					baidu: 'https://www.baidu.com/s?wd=',
				}};
		const sidebarToggle = document.getElementById('sidebarToggle');
		const defaultIconSrc = '{escape(DEFAULT_ICON_DATA_URI, quote=True)}';
		const sidebarStateKey = 'favorite-navigation-sidebar-collapsed';
		const navStatePrefix = 'favorite-navigation-nav-collapsed:';
		const searchEngineDropdownGap = 8;
		const searchEngineDropdownWidth = 220;

		// Search engine dropdown handlers
		function positionSearchEngineDropdown() {{
			const rect = searchEngineSelector.getBoundingClientRect();
			const availableRight = Math.max(window.innerWidth - rect.left - 16, searchEngineDropdownWidth);
			searchEngineDropdown.style.position = 'fixed';
			searchEngineDropdown.style.left = `${{Math.max(12, rect.left)}}px`;
			searchEngineDropdown.style.top = `${{rect.bottom + searchEngineDropdownGap}}px`;
			searchEngineDropdown.style.width = `${{Math.max(rect.width, searchEngineDropdownWidth, availableRight)}}px`;
		}}

		function ensureSearchEngineDropdownPortal() {{
			if (searchEngineDropdown.parentElement !== document.body) {{
				document.body.appendChild(searchEngineDropdown);
			}}
		}}

		function openSearchEngineDropdown() {{
			ensureSearchEngineDropdownPortal();
			positionSearchEngineDropdown();
			searchEngineSelector.dataset.open = 'true';
			searchEngineDropdown.dataset.visible = 'true';
		}}

		function closeSearchEngineDropdown() {{
			searchEngineSelector.dataset.open = 'false';
			searchEngineDropdown.dataset.visible = 'false';
		}}

		// Click on the selector to open/close dropdown
		searchEngineSelector.addEventListener('click', (e) => {{
			e.preventDefault();
			e.stopPropagation();
			const isOpen = searchEngineDropdown.dataset.visible === 'true';
			if (isOpen) {{
				closeSearchEngineDropdown();
			}} else {{
				openSearchEngineDropdown();
			}}
		}});

		searchEngineItems.forEach((item) => {{
			item.addEventListener('click', (e) => {{
				e.preventDefault();
				e.stopPropagation();
				const value = item.dataset.value;
				const label = item.dataset.label;
				
				// Update select element
				webSearchEngine.value = value;
				
				// Update display
				selectedEngineDisplay.textContent = label;
				
				// Update UI states
				searchEngineItems.forEach((i) => {{
					i.dataset.selected = i === item ? 'true' : 'false';
				}});
				
				closeSearchEngineDropdown();
			}});
		}});

		// Close dropdown when clicking outside
		document.addEventListener('click', (e) => {{
			if (!searchEngineSelector.contains(e.target) && !searchEngineDropdown.contains(e.target)) {{
				closeSearchEngineDropdown();
			}}
		}});

		// Close dropdown on Escape key
		document.addEventListener('keydown', (e) => {{
			if (e.key === 'Escape') {{
				closeSearchEngineDropdown();
			}}
		}});

		// Handle window resize to reposition dropdown
		window.addEventListener('resize', () => {{
			if (searchEngineDropdown.dataset.visible === 'true') {{
				positionSearchEngineDropdown();
			}}
		}});

		window.addEventListener('scroll', () => {{
			if (searchEngineDropdown.dataset.visible === 'true') {{
				positionSearchEngineDropdown();
			}}
		}}, true);

		function normalize(value) {{
			return (value || '').toLowerCase().trim();
		}}

		function setSidebarCollapsed(collapsed) {{
			layout.dataset.sidebarCollapsed = collapsed ? 'true' : 'false';
			sidebarToggle.setAttribute('aria-expanded', String(!collapsed));
			sidebarToggle.querySelector('.sidebar-toggle-text').textContent = collapsed ? '展开' : '收起';
			sidebarToggle.querySelector('.sidebar-toggle-icon').textContent = collapsed ? '⟩' : '⟨';
			try {{
				localStorage.setItem(sidebarStateKey, String(collapsed));
			}} catch (error) {{
				void error;
			}}
		}}

		try {{
			setSidebarCollapsed(localStorage.getItem(sidebarStateKey) === 'true');
		}} catch (error) {{
			void error;
		}}

		sidebarToggle.addEventListener('click', () => {{
			setSidebarCollapsed(layout.dataset.sidebarCollapsed !== 'true');
		}});

		function navStateKey(navId) {{
			return navStatePrefix + navId;
		}}

		function setNavCollapsed(button, collapsed, persist = true) {{
			const item = button.closest('.nav-item');
			if (!item) {{
				return;
			}}
			item.dataset.collapsed = collapsed ? 'true' : 'false';
			button.setAttribute('aria-expanded', String(!collapsed));
			const folderTitle = button.dataset.folderTitle || '';
			button.setAttribute('aria-label', `${{collapsed ? '展开' : '折叠'}} ${{folderTitle}}`);
			const icon = button.querySelector('span');
			if (icon) {{
				icon.textContent = collapsed ? '▸' : '▾';
			}}
			if (persist) {{
				try {{
					const navId = item.dataset.navId;
					if (navId) {{
						localStorage.setItem(navStateKey(navId), String(collapsed));
					}}
				}} catch (error) {{
					void error;
				}}
			}}
		}}

		navItems.forEach((item) => {{
			const button = item.querySelector('.nav-fold-toggle');
			if (!button) {{
				return;
			}}
			try {{
				const stored = localStorage.getItem(navStateKey(item.dataset.navId || ''));
				if (stored === 'true') {{
					setNavCollapsed(button, true, false);
				}} else {{
					setNavCollapsed(button, false, false);
				}}
			}} catch (error) {{
				void error;
				setNavCollapsed(button, false, false);
			}}
		}});

		document.querySelectorAll('.bookmark-favicon').forEach((img) => {{
			img.addEventListener('error', () => {{
				if (img.dataset.fallbackApplied === 'true') {{
					return;
				}}
				img.dataset.fallbackApplied = 'true';
				img.src = defaultIconSrc;
				img.classList.add('is-default');
			}});
		}});

		function updateVisibility() {{
			const query = normalize(input.value);
			let visibleFolders = 0;

			folders.forEach((folder) => {{
				const items = Array.from(folder.querySelectorAll('.bookmark-card'));
				const folderMatch = normalize(folder.dataset.search).includes(query);
				let bookmarkMatch = false;

				items.forEach((item) => {{
					const matched = query === '' || normalize(item.dataset.search).includes(query);
					item.style.display = matched ? '' : 'none';
					bookmarkMatch = bookmarkMatch || matched;
				}});

				const shouldShow = query === '' || folderMatch || bookmarkMatch;
				folder.style.display = shouldShow ? '' : 'none';
				folder.dataset.filtered = shouldShow ? 'false' : 'true';

				if (query !== '') {{
					folder.dataset.collapsed = shouldShow ? 'false' : 'true';
				}}

				if (shouldShow) visibleFolders += 1;
			}});

			document.getElementById('content').style.minHeight = visibleFolders ? 'auto' : '160px';
			let empty = document.getElementById('emptyState');
			if (!empty) {{
				empty = document.createElement('div');
				empty.id = 'emptyState';
				empty.className = 'empty';
				empty.textContent = '没有找到匹配的收藏，请尝试缩短关键词或切换搜索词。';
				document.getElementById('content').appendChild(empty);
			}}
			empty.style.display = visibleFolders ? 'none' : 'block';
		}}

		input.addEventListener('input', updateVisibility);
		webSearchForm.addEventListener('submit', (event) => {{
			event.preventDefault();
			const query = (webSearchInput.value || '').trim();
			if (!query) {{
				webSearchInput.focus();
				return;
			}}
			const engine = webSearchEngine.value in webSearchUrls ? webSearchEngine.value : 'bing';
			const targetUrl = webSearchUrls[engine] + encodeURIComponent(query);
			window.open(targetUrl, '_blank', 'noopener,noreferrer');
		}});

		document.querySelectorAll('.folder-toggle').forEach((button) => {{
			button.addEventListener('click', () => {{
				const card = button.closest('.folder-card');
				const collapsed = card.dataset.collapsed === 'true';
				card.dataset.collapsed = collapsed ? 'false' : 'true';
				button.setAttribute('aria-expanded', String(collapsed));
				button.textContent = collapsed ? '收起' : '展开';
			}});
		}});

		document.querySelectorAll('.nav-fold-toggle').forEach((button) => {{
			button.addEventListener('click', () => {{
				const item = button.closest('.nav-item');
				if (!item) {{
					return;
				}}
				const collapsed = item.dataset.collapsed === 'true';
				setNavCollapsed(button, !collapsed);
			}});
		}});

		updateVisibility();
	</script>
</body>
</html>"""


def main() -> None:
	base_dir = Path(__file__).resolve().parent
	source_path = base_dir / "data.html"
	output_path = base_dir / "favorites_navigation.html"

	root = parse_bookmarks(source_path)
	html = build_html(root, source_path.name)
	output_path.write_text(html, encoding="utf-8")
	print(f"generated: {output_path}")


if __name__ == "__main__":
	main()
