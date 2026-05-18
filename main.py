"""
浏览器书签HTML转换工具
支持将 Chrome/Edge 导出的书签 HTML 文件转换为美观的静态网页
"""

import html
import re
from pathlib import Path
from typing import List, Dict
from dataclasses import dataclass, field


@dataclass
class Bookmark:
    """书签数据结构"""
    title: str
    url: str
    folder: str = ""
    add_date: str = ""
    icon: str = ""

    @property
    def domain(self) -> str:
        """提取域名用于图标显示"""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(self.url)
            return parsed.netloc or "unknown"
        except:
            return "unknown"


@dataclass
class BookmarkFolder:
    """书签文件夹"""
    name: str
    bookmarks: List[Bookmark] = field(default_factory=list)
    subfolders: Dict[str, 'BookmarkFolder'] = field(default_factory=dict)

    def add_bookmark(self, bookmark: Bookmark):
        """添加书签到当前文件夹"""
        self.bookmarks.append(bookmark)

    def get_or_create_subfolder(self, name: str) -> 'BookmarkFolder':
        """获取或创建子文件夹"""
        if name not in self.subfolders:
            self.subfolders[name] = BookmarkFolder(name=name)
        return self.subfolders[name]

    def count_bookmarks(self) -> int:
        """统计所有书签数量（包括子文件夹）"""
        count = len(self.bookmarks)
        for subfolder in self.subfolders.values():
            count += subfolder.count_bookmarks()
        return count


class BookmarkParser:
    """解析浏览器导出的书签 HTML"""

    # DT 匹配模式 - 匹配 <DT><H3> 或 <DT><A> 标签
    DT_PATTERN = re.compile(r'<DT>(<H3[^>]*>.*?</H3>|<A[^>]*>.*?</A>)', re.IGNORECASE | re.DOTALL)
    DL_END_PATTERN = re.compile(r'</DL>', re.IGNORECASE)

    # 提取属性
    HREF_ATTR = re.compile(r'HREF\s*=\s*"([^"]*)"', re.IGNORECASE)
    ADD_DATE_ATTR = re.compile(r'ADD_DATE\s*=\s*"([^"]*)"', re.IGNORECASE)
    ICON_ATTR = re.compile(r'ICON\s*=\s*"([^"]*)"', re.IGNORECASE)

    def __init__(self, html_content: str):
        self.html_content = html_content

    def parse(self) -> BookmarkFolder:
        """解析书签 HTML，返回文件夹树结构"""
        root = BookmarkFolder(name="根目录")
        current_folder = root
        folder_stack = [root]

        # 找到所有 DT 和 DL 结束标签的位置
        positions = []
        for match in self.DT_PATTERN.finditer(self.html_content):
            positions.append(('DT', match.start(), match))
        for match in self.DL_END_PATTERN.finditer(self.html_content):
            positions.append(('DL_END', match.start(), match))

        # 按位置排序
        positions.sort(key=lambda x: x[1])

        # 处理每个元素
        for pos_type, _, match in positions:
            if pos_type == 'DT':
                element = match.group(1)

                if element.upper().startswith('<H3'):
                    # 开始新文件夹
                    folder_name = self._extract_text(element)
                    if folder_name:
                        current_folder = current_folder.get_or_create_subfolder(folder_name)
                        folder_stack.append(current_folder)

                elif element.upper().startswith('<A'):
                    # 书签链接
                    bookmark = self._parse_link(element)
                    if bookmark.url:
                        bookmark.folder = current_folder.name if current_folder.name != "根目录" else ""
                        current_folder.add_bookmark(bookmark)

            elif pos_type == 'DL_END':
                # 结束当前文件夹
                if len(folder_stack) > 1:
                    folder_stack.pop()
                    current_folder = folder_stack[-1]

        return root

    def _extract_text(self, element: str) -> str:
        """提取标签内的纯文本"""
        # 移除 HTML 标签
        text = re.sub(r'<[^>]+>', '', element)
        return html.unescape(text).strip()

    def _parse_link(self, element: str) -> Bookmark:
        """解析链接元素"""
        # 提取 URL
        href_match = self.HREF_ATTR.search(element)
        url = href_match.group(1) if href_match else ""

        # 提取标题
        title_match = re.search(r'>(.*?)</A>', element, re.IGNORECASE | re.DOTALL)
        title = title_match.group(1) if title_match else url
        title = html.unescape(re.sub(r'<[^>]+>', '', title)).strip()

        # 提取添加日期
        date_match = self.ADD_DATE_ATTR.search(element)
        add_date = date_match.group(1) if date_match else ""

        # 提取图标
        icon_match = self.ICON_ATTR.search(element)
        icon = icon_match.group(1) if icon_match else ""

        return Bookmark(
            title=title or "Untitled",
            url=url,
            add_date=add_date,
            icon=icon
        )


class StaticPageGenerator:
    """生成静态网页 HTML"""

    def __init__(self, folder: BookmarkFolder, title: str = "我的书签"):
        self.folder = folder
        self.title = title
        self.total_bookmarks = folder.count_bookmarks()

    def generate(self, output_path: str):
        """生成静态网页"""
        html_content = self._build_html()
        Path(output_path).write_text(html_content, encoding='utf-8')

    def _build_html(self) -> str:
        """构建完整的 HTML 页面"""
        return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{self.title}</title>
    <style>{self._get_css()}</style>
</head>
<body>
    <div class="container">
        <header>
            <div class="header-top">
                <h1>📚 {self.title}</h1>
                <div class="stats">
                    <span class="stat-item">📁 {self._count_folders(self.folder)}</span>
                    <span class="stat-item">🔗 {self.total_bookmarks}</span>
                </div>
            </div>

            <div class="web-search-container">
                <div class="web-search-box">
                    <select id="engineSelect" class="engine-select" onchange="switchEngine(this.value)">
                        <option value="google">谷歌</option>
                        <option value="bing">必应</option>
                        <option value="baidu">百度</option>
                        <option value="sogou">搜狗</option>
                        <option value="duckduckgo">DuckDuckGo</option>
                    </select>
                    <input type="text" id="webSearchInput" placeholder="🌐 网页搜索..." onkeypress="handleWebSearchKeypress(event)">
                    <button class="search-btn" onclick="performWebSearch()">🔍</button>
                </div>
            </div>

            <div class="bookmark-search-box">
                <input type="text" id="searchInput" placeholder="🔍 搜索书签..." oninput="handleSearch(this.value)">
                <button id="clearSearch" class="clear-btn" onclick="clearSearch()" style="display:none;">✕</button>
            </div>
        </header>

        <div class="layout-wrapper">
            <nav class="sidebar">
                <div class="sidebar-header">
                    <h3>📂 文件夹导航</h3>
                    <button class="collapse-all-btn" onclick="collapseAllNav()">全部折叠</button>
                    <button class="expand-all-btn" onclick="expandAllNav()">全部展开</button>
                </div>
                <ul class="nav-list">
                    {self._generate_nav_items(self.folder, 0)}
                </ul>
            </nav>

            <main class="content">
                <div id="searchResults" class="search-results" style="display:none;">
                    <div class="search-results-header">
                        <h2>🔍 搜索结果</h2>
                        <button onclick="clearSearch()">关闭</button>
                    </div>
                    <div id="searchResultsContent" class="search-results-content"></div>
                </div>

                <div id="mainContent">
                    {self._generate_content(self.folder)}
                </div>
            </main>
        </div>

    </div>

    <script>{self._get_js()}</script>
</body>
</html>'''

    def _count_folders(self, folder: BookmarkFolder) -> int:
        """统计文件夹数量"""
        count = 0
        if folder.subfolders:
            count += len(folder.subfolders)
            for subfolder in folder.subfolders.values():
                count += self._count_folders(subfolder)
        return count

    def _generate_nav_items(self, folder: BookmarkFolder, level: int = 0, parent_path: str = "") -> str:
        """生成侧边栏导航项 - 按文件夹层级递归生成"""
        if not folder.subfolders:
            return ""

        items = []

        for name, subfolder in folder.subfolders.items():
            current_path = f"{parent_path}/{name}" if parent_path else name
            safe_id = self._make_id(current_path)
            count = subfolder.count_bookmarks()
            level_class = f"nav-level-{level}"

            if subfolder.subfolders:
                # 有子文件夹，添加折叠按钮
                sub_nav = self._generate_nav_items(subfolder, level + 1, current_path)
                items.append(f'''<li class="nav-item {level_class}">
                    <div class="nav-item-header">
                        <button class="toggle-btn" onclick="toggleNav(this)" aria-expanded="true">
                            <span class="toggle-icon">▼</span>
                        </button>
                        <a href="#{safe_id}" onclick="highlightSection('{safe_id}')" title="{current_path}">{name}</a>
                        <span class="bookmark-count">({count})</span>
                    </div>
                    {sub_nav}
                </li>''')
            else:
                # 无子文件夹，普通链接
                items.append(f'''<li class="nav-item {level_class}">
                    <div class="nav-item-header nav-leaf">
                        <a href="#{safe_id}" onclick="highlightSection('{safe_id}')" title="{current_path}">{name}</a>
                        <span class="bookmark-count">({count})</span>
                    </div>
                </li>''')

        if level == 0:
            return "\n            ".join(items)
        return f'<ul class="nav-sublist nav-level-{level}">\n                ' + "\n                ".join(items) + "\n            </ul>"

    def _generate_content(self, folder: BookmarkFolder) -> str:
        """生成主内容区域"""
        sections = []

        # 生成根目录书签（如果有）
        if folder.bookmarks:
            sections.append(self._generate_bookmarks_section("", folder.bookmarks))

        # 生成子文件夹
        for name, subfolder in folder.subfolders.items():
            sections.append(self._generate_folder_section(name, subfolder))

        return "\n\n".join(sections)

    def _generate_folder_section(self, name: str, folder: BookmarkFolder, parent_path: str = "") -> str:
        """生成单个文件夹的章节"""
        current_path = f"{parent_path}/{name}" if parent_path else name
        safe_id = self._make_id(current_path)
        breadcrumb = f" {parent_path} ›" if parent_path else ""

        section = f'''
        <section id="{safe_id}" class="folder-section">
            <h2 class="folder-title">📂 {self._escape_html(name)}<small class="breadcrumb">{breadcrumb}</small></h2>
            <p class="folder-meta">包含 {len(folder.bookmarks)} 个书签</p>
            {self._generate_bookmarks_grid(folder.bookmarks)}
        '''

        # 递归生成子文件夹
        for sub_name, subfolder in folder.subfolders.items():
            section += self._generate_folder_section(sub_name, subfolder, current_path)

        section += "\n        </section>"
        return section

    def _generate_bookmarks_section(self, title: str, bookmarks: List[Bookmark]) -> str:
        """生成书签列表"""
        if not bookmarks:
            return ""

        header = f'<h2 class="folder-title">🔗 {title or "未分类书签"}</h2>' if title else ""
        return f'''
        <section class="folder-section">
            {header}
            {self._generate_bookmarks_grid(bookmarks)}
        </section>'''

    def _generate_bookmarks_grid(self, bookmarks: List[Bookmark]) -> str:
        """生成书签网格"""
        return f'<div class="bookmarks-grid">\n' + "\n".join(
            self._generate_bookmark_card(bm) for bm in bookmarks
        ) + "\n        </div>"

    def _generate_bookmark_card(self, bookmark: Bookmark) -> str:
        """生成单个书签卡片"""
        return f'''        <div class="bookmark-card" data-title="{bookmark.title.lower()}" data-url="{bookmark.url.lower()}">
            <div class="bookmark-icon">
                <img src="https://www.google.com/s2/favicons?domain={bookmark.domain}&sz=64"
                     alt="" onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 24 24%22 fill=%22%23999%22><path d=%22M5 5v14h14V5H5zm12 12H7V7h10v10z%22/></svg>'">
            </div>
            <div class="bookmark-info">
                <a href="{bookmark.url}" target="_blank" class="bookmark-title">{self._escape_html(bookmark.title)}</a>
                <span class="bookmark-url">{bookmark.domain}</span>
            </div>
        </div>'''

    def _make_id(self, text: str) -> str:
        """生成安全的 HTML ID"""
        return re.sub(r'[^\w一-鿿-]', '_', text)

    def _escape_html(self, text: str) -> str:
        """转义 HTML 特殊字符"""
        return html.escape(text)

    def _get_css(self) -> str:
        """获取 CSS 样式"""
        return '''
        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Microsoft YaHei", sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            height: 100vh;
            margin: 0;
            padding: 10px;
            color: #333;
            overflow: hidden;
        }

        .container {
            max-width: 1400px;
            width: 100%;
            height: 100%;
            margin: 0 auto;
            background: white;
            border-radius: 12px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.3);
            overflow: hidden;
            display: grid;
            grid-template-rows: auto 1fr;
        }

        header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 8px 20px;
        }

        .header-top {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
        }

        header h1 {
            font-size: 1.2rem;
            margin: 0;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.2);
        }

        .stats {
            display: flex;
            gap: 8px;
        }

        .stat-item {
            background: rgba(255,255,255,0.2);
            padding: 3px 8px;
            border-radius: 10px;
            font-size: 0.7rem;
        }

        /* 网页搜索容器 */
        .web-search-container {
            max-width: 600px;
            margin: 0 auto 6px;
        }

        .web-search-box {
            display: flex;
            gap: 8px;
            align-items: center;
        }

        .engine-select {
            background: white;
            color: #667eea;
            border: none;
            padding: 6px 10px;
            border-radius: 18px 0 0 18px;
            cursor: pointer;
            font-size: 0.8rem;
            font-weight: 600;
            outline: none;
            flex-shrink: 0;
        }

        .web-search-box input {
            flex: 1;
            padding: 6px 12px;
            border: none;
            font-size: 0.85rem;
            outline: none;
            background: rgba(255,255,255,0.2);
            color: white;
        }

        .web-search-box input::placeholder {
            color: rgba(255,255,255,0.7);
        }

        .web-search-box input:focus {
            background: rgba(255,255,255,0.3);
        }

        .search-btn {
            background: white;
            color: #667eea;
            border: none;
            padding: 6px 14px;
            border-radius: 18px;
            cursor: pointer;
            font-size: 0.85rem;
            transition: all 0.2s;
        }

        .search-btn:hover {
            transform: scale(1.05);
            box-shadow: 0 2px 10px rgba(0,0,0,0.2);
        }

        /* 书签搜索框 */
        .bookmark-search-box {
            position: relative;
            display: flex;
            justify-content: center;
            align-items: center;
            margin-top: 5px;
        }

        .bookmark-search-box input {
            width: 100%;
            max-width: 400px;
            padding: 5px 30px 5px 12px;
            border: none;
            border-radius: 12px;
            font-size: 0.8rem;
            outline: none;
            background: rgba(255,255,255,0.2);
            color: white;
            box-shadow: none;
        }

        .bookmark-search-box input::placeholder {
            color: rgba(255,255,255,0.7);
        }

        .bookmark-search-box input:focus {
            background: rgba(255,255,255,0.3);
        }

        .clear-btn {
            position: absolute;
            right: calc(50% - 175px);
            background: rgba(255,255,255,0.3);
            border: none;
            width: 18px;
            height: 18px;
            border-radius: 50%;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 11px;
            transition: background 0.2s;
        }

        .clear-btn:hover {
            background: rgba(255,255,255,0.5);
        }

        .layout-wrapper {
            display: grid;
            grid-template-columns: 300px 1fr;
            min-height: 0;
        }

        .sidebar {
            background: #f8f9fa;
            border-right: 1px solid #e9ecef;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }

        .sidebar-header {
            padding: 10px 15px 8px;
            border-bottom: 1px solid #e9ecef;
            display: flex;
            flex-direction: column;
            gap: 6px;
        }

        .sidebar-header h3 {
            font-size: 0.9rem;
            color: #495057;
            margin: 0;
        }

        .sidebar-header button {
            background: none;
            border: 1px solid #dee2e6;
            padding: 3px 8px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 0.7rem;
            color: #6c757d;
            transition: all 0.2s;
        }

        .sidebar-header button:hover {
            background: #e9ecef;
            color: #495057;
        }

        .nav-list {
            list-style: none;
            overflow-y: auto;
            flex: 1;
            padding: 8px;
        }

        .nav-item {
            margin-bottom: 1px;
            position: relative;
        }

        .nav-item-header {
            display: flex;
            align-items: center;
            gap: 4px;
            padding: 3px 6px;
            padding-left: 10px;
            border-radius: 5px;
            transition: background 0.2s;
        }

        /* 叶子节点（无子文件夹）的左边距 */
        .nav-item-header.nav-leaf {
            padding-left: 26px;
        }

        /* 层级缩进 */
        .nav-level-0 > .nav-item > .nav-item-header {
            padding-left: 6px;
        }

        .nav-level-1 > .nav-item > .nav-item-header {
            padding-left: 6px;
        }

        .nav-level-1 > .nav-item > .nav-item-header.nav-leaf {
            padding-left: 22px;
        }

        .nav-level-2 > .nav-item > .nav-item-header {
            padding-left: 6px;
        }

        .nav-level-2 > .nav-item > .nav-item-header.nav-leaf {
            padding-left: 22px;
        }

        .nav-item-header:hover {
            background: #e9ecef;
        }

        .toggle-btn {
            background: none;
            border: none;
            cursor: pointer;
            padding: 0;
            width: 16px;
            height: 16px;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
            transition: transform 0.2s;
        }

        .toggle-btn .toggle-icon {
            font-size: 9px;
            color: #6c757d;
            transition: transform 0.2s;
        }

        .toggle-btn[aria-expanded="false"] .toggle-icon {
            transform: rotate(-90deg);
        }

        .nav-spacer {
            width: 18px;
            flex-shrink: 0;
        }

        .nav-list a {
            color: #495057;
            text-decoration: none;
            flex: 1;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            font-size: 0.85rem;
        }

        .nav-list a:hover {
            color: #667eea;
        }

        .bookmark-count {
            color: #adb5bd;
            font-size: 0.7rem;
            flex-shrink: 0;
        }

        .nav-sublist {
            list-style: none;
            padding-left: 16px;
            overflow: hidden;
            transition: max-height 0.3s ease-out, opacity 0.2s ease-out;
            max-height: 5000px;
            opacity: 1;
        }

        .nav-sublist.collapsed {
            max-height: 0;
            opacity: 0;
        }

        /* 层级显示样式 */
        .nav-level-0 .nav-item-header {
            font-weight: 600;
            font-size: 0.85rem;
        }

        .nav-level-1 .nav-item-header {
            font-weight: 500;
            font-size: 0.8rem;
        }

        .nav-level-2 .nav-item-header,
        .nav-level-3 .nav-item-header {
            font-weight: 400;
            font-size: 0.78rem;
        }

        /* 子层级左侧边框线 */
        .nav-sublist {
            position: relative;
        }

        .nav-sublist::before {
            content: '';
            position: absolute;
            left: 6px;
            top: 4px;
            bottom: 4px;
            width: 1px;
            background: #dee2e6;
        }

        .nav-sublist .nav-item::before {
            content: '';
            position: absolute;
            left: 6px;
            top: 50%;
            width: 6px;
            height: 1px;
            background: #dee2e6;
        }

        .nav-sublist .nav-item:last-child::after {
            content: '';
            position: absolute;
            left: 6px;
            top: 50%;
            bottom: 0;
            width: 1px;
            background: white;
        }

        .content {
            padding: 15px 20px;
            overflow-y: auto;
            overflow-x: hidden;
        }

        /* 搜索结果样式 */
        .search-results {
            background: #f8f9fa;
            border-radius: 10px;
            padding: 15px;
            margin-bottom: 20px;
            border: 2px solid #667eea;
        }

        .search-results-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 1px solid #e9ecef;
        }

        .search-results-header h2 {
            font-size: 1.1rem;
            color: #667eea;
        }

        .search-results-header button {
            background: white;
            border: 1px solid #dee2e6;
            padding: 6px 12px;
            border-radius: 6px;
            cursor: pointer;
            transition: all 0.2s;
            font-size: 0.85rem;
        }

        .search-results-header button:hover {
            background: #e9ecef;
        }

        .search-results-content {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 12px;
        }

        .search-result-item {
            background: white;
            border-radius: 8px;
            padding: 12px;
            border: 1px solid #e9ecef;
            transition: all 0.2s;
        }

        .search-result-item:hover {
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
            border-color: #667eea;
        }

        .search-result-item.match-title {
            border-left: 4px solid #28a745;
        }

        .search-result-item.match-url {
            border-left: 4px solid #ffc107;
        }

        .search-result-folder {
            font-size: 0.7rem;
            color: #6c757d;
            margin-bottom: 6px;
            display: flex;
            align-items: center;
            gap: 4px;
        }

        .search-result-folder::before {
            content: "📁";
        }

        .folder-section {
            margin-bottom: 25px;
            scroll-margin-top: 10px;
        }

        .folder-section.highlight {
            animation: highlight 2s ease-out;
        }

        @keyframes highlight {
            0% { background: rgba(102, 126, 234, 0.2); }
            100% { background: transparent; }
        }

        .folder-title {
            font-size: 1.2rem;
            color: #495057;
            margin-bottom: 8px;
            padding-bottom: 8px;
            border-bottom: 2px solid #e9ecef;
        }

        .folder-title .breadcrumb {
            font-size: 0.75rem;
            color: #adb5bd;
            font-weight: 400;
            margin-left: 8px;
        }

        .folder-meta {
            color: #6c757d;
            font-size: 0.8rem;
            margin-bottom: 12px;
        }

        .bookmarks-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
            gap: 12px;
        }

        .bookmark-card {
            display: flex;
            align-items: center;
            padding: 10px 12px;
            background: #f8f9fa;
            border-radius: 8px;
            transition: all 0.3s;
            text-decoration: none;
            border: 1px solid transparent;
        }

        .bookmark-card:hover {
            background: white;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
            transform: translateY(-2px);
            border-color: #667eea;
        }

        .bookmark-icon {
            width: 32px;
            height: 32px;
            flex-shrink: 0;
            margin-right: 10px;
        }

        .bookmark-icon img {
            width: 24px;
            height: 24px;
            border-radius: 5px;
        }

        .bookmark-info {
            flex: 1;
            min-width: 0;
        }

        .bookmark-title {
            color: #212529;
            text-decoration: none;
            font-weight: 500;
            font-size: 0.9rem;
            display: block;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        .bookmark-title:hover {
            color: #667eea;
        }

        .bookmark-url {
            color: #6c757d;
            font-size: 0.75rem;
            display: block;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        @media (max-width: 768px) {
            body {
                padding: 5px;
            }
            .container {
                border-radius: 8px;
            }
            .layout-wrapper {
                grid-template-columns: 1fr;
            }
            .sidebar {
                max-height: 150px;
                border-right: none;
                border-bottom: 1px solid #e9ecef;
            }
            .bookmarks-grid, .search-results-content {
                grid-template-columns: 1fr;
            }
            .header-top {
                flex-direction: column;
                gap: 6px;
                text-align: center;
            }
            .stats {
                justify-content: center;
            }
            .web-search-container {
                max-width: 100%;
            }
            .engine-select {
                flex-shrink: 0;
                min-width: 70px;
            }
            .content {
                padding: 12px;
            }
        }

        @media print {
            body { background: white; padding: 0; }
            .container { box-shadow: none; border-radius: 0; }
            .sidebar, .web-search-container, .bookmark-search-box { display: none; }
            .bookmark-card { break-inside: avoid; }
            .search-results { page-break-before: always; }
        }
        '''

    def _get_js(self) -> str:
        """获取 JavaScript 代码"""
        return '''
        // 搜索引擎配置
        const searchEngines = {
            google: {
                name: '谷歌',
                url: 'https://www.google.com/search?q=',
                placeholder: '🌐 谷歌搜索...'
            },
            bing: {
                name: '必应',
                url: 'https://www.bing.com/search?q=',
                placeholder: '🌐 必应搜索...'
            },
            baidu: {
                name: '百度',
                url: 'https://www.baidu.com/s?wd=',
                placeholder: '🌐 百度搜索...'
            },
            sogou: {
                name: '搜狗',
                url: 'https://www.sogou.com/web?query=',
                placeholder: '🌐 搜狗搜索...'
            },
            duckduckgo: {
                name: 'DuckDuckGo',
                url: 'https://duckduckgo.com/?q=',
                placeholder: '🌐 DuckDuckGo 搜索...'
            }
        };

        let currentEngine = 'google';

        // 切换搜索引擎
        function switchEngine(engine) {
            currentEngine = engine;
            document.getElementById('engineSelect').value = engine;
            const input = document.getElementById('webSearchInput');
            input.placeholder = searchEngines[engine].placeholder;
            input.focus();
        }

        // 处理网页搜索回车键
        function handleWebSearchKeypress(event) {
            if (event.key === 'Enter') {
                performWebSearch();
            }
        }

        // 执行网页搜索
        function performWebSearch() {
            const query = document.getElementById('webSearchInput').value.trim();
            if (query) {
                const engine = searchEngines[currentEngine];
                const searchUrl = engine.url + encodeURIComponent(query);
                window.open(searchUrl, '_blank');
            }
        }

        // 存储所有书签数据用于搜索
        const allBookmarks = [];

        // 初始化：收集所有书签数据
        function initBookmarks() {
            document.querySelectorAll('.bookmark-card').forEach(card => {
                const titleEl = card.querySelector('.bookmark-title');
                const folderSection = card.closest('.folder-section');
                allBookmarks.push({
                    title: titleEl ? titleEl.textContent : '',
                    url: card.dataset.url || '',
                    domain: card.dataset.url ? new URL(card.dataset.url).hostname : '',
                    folder: folderSection ? folderSection.querySelector('.folder-title')?.firstChild?.textContent || '' : '',
                    element: card.outerHTML
                });
            });
        }

        // 搜索处理
        function handleSearch(query) {
            const searchResults = document.getElementById('searchResults');
            const searchResultsContent = document.getElementById('searchResultsContent');
            const mainContent = document.getElementById('mainContent');
            const clearBtn = document.getElementById('clearSearch');

            if (!query.trim()) {
                searchResults.style.display = 'none';
                mainContent.style.display = 'block';
                clearBtn.style.display = 'none';
                return;
            }

            const lowerQuery = query.toLowerCase();
            const results = allBookmarks.filter(bm =>
                bm.title.toLowerCase().includes(lowerQuery) ||
                bm.url.toLowerCase().includes(lowerQuery) ||
                bm.domain.toLowerCase().includes(lowerQuery)
            );

            searchResultsContent.innerHTML = '';

            if (results.length === 0) {
                searchResultsContent.innerHTML = '<p style="grid-column: 1/-1; text-align: center; color: #6c757d; padding: 40px;">未找到匹配的书签</p>';
            } else {
                results.forEach(bm => {
                    const matchType = bm.title.toLowerCase().includes(lowerQuery) ? 'match-title' : 'match-url';
                    const div = document.createElement('div');
                    div.className = `search-result-item ${matchType}`;
                    div.innerHTML = `
                        <div class="search-result-folder">${bm.folder}</div>
                        ${bm.element}
                    `;
                    searchResultsContent.appendChild(div);
                });
            }

            searchResults.style.display = 'block';
            mainContent.style.display = 'none';
            clearBtn.style.display = 'flex';
        }

        // 清除搜索
        function clearSearch() {
            const searchInput = document.getElementById('searchInput');
            searchInput.value = '';
            handleSearch('');
        }

        // 导航折叠/展开
        function toggleNav(btn) {
            const isExpanded = btn.getAttribute('aria-expanded') === 'true';
            btn.setAttribute('aria-expanded', !isExpanded);

            const sublist = btn.closest('.nav-item').querySelector('.nav-sublist');
            if (sublist) {
                sublist.classList.toggle('collapsed', isExpanded);
            }
        }

        // 全部折叠
        function collapseAllNav() {
            document.querySelectorAll('.toggle-btn[aria-expanded="true"]').forEach(btn => {
                btn.setAttribute('aria-expanded', 'false');
                const sublist = btn.closest('.nav-item').querySelector('.nav-sublist');
                if (sublist) sublist.classList.add('collapsed');
            });
        }

        // 全部展开
        function expandAllNav() {
            document.querySelectorAll('.toggle-btn[aria-expanded="false"]').forEach(btn => {
                btn.setAttribute('aria-expanded', 'true');
                const sublist = btn.closest('.nav-item').querySelector('.nav-sublist');
                if (sublist) sublist.classList.remove('collapsed');
            });
        }

        // 高亮章节
        function highlightSection(id) {
            setTimeout(() => {
                const section = document.getElementById(id);
                if (section) {
                    section.classList.remove('highlight');
                    void section.offsetWidth; // 触发重排
                    section.classList.add('highlight');
                }
            }, 100);
        }

        // 平滑滚动
        document.querySelectorAll('a[href^="#"]').forEach(anchor => {
            anchor.addEventListener('click', function(e) {
                const href = this.getAttribute('href');
                if (href !== '#') {
                    e.preventDefault();
                    const target = document.querySelector(href);
                    if (target) {
                        target.scrollIntoView({ behavior: 'smooth', block: 'start' });
                    }
                }
            });
        });

        // 键盘快捷键
        document.addEventListener('keydown', function(e) {
            // ESC 清除搜索
            if (e.key === 'Escape') {
                clearSearch();
            }
            // / 聚焦搜索框
            if (e.key === '/' && !e.ctrlKey && !e.metaKey) {
                const searchInput = document.getElementById('searchInput');
                if (document.activeElement !== searchInput) {
                    e.preventDefault();
                    searchInput.focus();
                }
            }
        });

        // 初始化
        document.addEventListener('DOMContentLoaded', initBookmarks);
        '''


def convert_bookmarks(input_file: str, output_file: str, title: str = "我的书签"):
    """
    转换浏览器书签文件

    Args:
        input_file: 输入的书签 HTML 文件路径
        output_file: 输出的静态网页文件路径
        title: 网页标题
    """
    input_path = Path(input_file)

    if not input_path.exists():
        raise FileNotFoundError(f"找不到文件: {input_file}")

    # 读取输入文件
    print(f"📖 正在读取书签文件: {input_file}")
    html_content = input_path.read_text(encoding='utf-8')

    # 解析书签
    print("🔍 正在解析书签结构...")
    parser = BookmarkParser(html_content)
    folder_tree = parser.parse()

    # 生成静态网页
    print(f"📝 正在生成静态网页...")
    generator = StaticPageGenerator(folder_tree, title=title)
    generator.generate(output_file)

    print(f"✅ 转换完成！")
    print(f"   文件夹数: {generator._count_folders(folder_tree)}")
    print(f"   书签数: {generator.total_bookmarks}")
    print(f"   输出文件: {output_file}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("""
📚 浏览器书签转换工具

使用方法:
  python main.py <输入文件> [输出文件] [标题]

参数说明:
  输入文件  - 浏览器导出的书签 HTML 文件路径
  输出文件  - 生成的静态网页文件路径 (默认: bookmarks.html)
  标题      - 网页标题 (默认: "我的书签")

示例:
  python main.py bookmarks.html
  python main.py edge_bookmarks.html my_bookmarks.html
  python main.py chrome.html output.html "我的Chrome书签"
        """)
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else "data.html"
    title = sys.argv[3] if len(sys.argv) > 3 else "我的书签"

    try:
        convert_bookmarks(input_file, output_file, title)
    except Exception as e:
        print(f"❌ 错误: {e}")
        sys.exit(1)
