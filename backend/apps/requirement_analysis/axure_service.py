# -*- coding: utf-8 -*-
"""
Axure在线原型解析服务
用于从Axure在线链接获取需求内容并解析
支持全量内容提取和增量内容（蓝色/红色标记）提取
与 arch-al-testcase-center 项目保持一致
"""
import os
import re
import time
import asyncio
import traceback
from typing import Dict, Optional, List
from urllib.parse import urlparse, unquote, parse_qs
from datetime import datetime

from backend.log_config import get_logger

logger = get_logger(__name__)

# 预先导入BeautifulSoup，确保可用
try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False
    logger.warning("BeautifulSoup 未安装，请运行: pip install beautifulsoup4")


class AxureService:
    """Axure在线原型解析服务"""

    def __init__(self):
        """初始化服务，从配置文件读取凭据"""
        from backend.config_loader import config_loader
        self.username = config_loader.get('AXURE.USERNAME', '')
        self.password = config_loader.get('AXURE.PASSWORD', '')

    def fetch_axure_content(self, url: str, wait_time: int = 5) -> Dict[str, str]:
        """
        使用无头浏览器获取Axure在线原型内容（同步版本）
        优化实现：更好地解析 Axure 页面结构，提取表格和结构化内容

        Args:
            url: Axure在线原型链接
            wait_time: 页面加载等待时间（秒）

        Returns:
            Dict with keys: 'full_content', 'incremental_content', 'success', 'message'
        """
        try:
            from playwright.sync_api import sync_playwright
            from bs4 import BeautifulSoup
        except ImportError as e:
            logger.error(f"请安装 playwright 和 beautifulsoup4: pip install playwright beautifulsoup4")
            return {
                'success': False,
                'message': '缺少依赖: playwright 或 beautifulsoup4，请运行: pip install playwright beautifulsoup4',
                'full_content': '',
                'incremental_content': ''
            }

        try:
            # 尝试导入 playwright_stealth（可选）
            try:
                from playwright_stealth import Stealth
                stealth_available = True
            except ImportError:
                stealth_available = False
                logger.info("playwright_stealth 未安装，跳过隐身模式")

            with sync_playwright() as p:
                # 启动无头浏览器
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    viewport={'width': 1920, 'height': 1080},
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                )
                page = context.new_page()

                # 使用stealth避免被检测（如果可用）
                if stealth_available:
                    try:
                        stealth = Stealth()
                        stealth.apply_stealth_sync(page)
                    except Exception as e:
                        logger.warning(f"Stealth 模式应用失败: {e}")

                logger.info(f"正在访问Axure链接: {url}")

                # 访问页面
                page.goto(url, wait_until='networkidle', timeout=60000)
                time.sleep(wait_time)

                # 处理登录
                if self.username and self.password:
                    self._handle_login(page)

                # 从 URL 解析页面名称
                parsed_url = urlparse(url)
                page_name = ""
                if 'p=' in url:
                    query_params = parse_qs(parsed_url.query)
                    if 'p' in query_params:
                        page_name = unquote(query_params['p'][0])

                time.sleep(2)

                # ============= 获取Axure主内容区域iframe =============
                logger.info("[Axure解析] 开始获取主内容区域...")

                iframe_content = ""

                # Axure典型的iframe名称/id列表
                main_frame_selectors = [
                    'iframe#mainFrame',
                    'iframe[name="mainFrame"]',
                    'iframe#mainPanel',
                    'iframe[name="mainPanel"]',
                    '#mainFrame',
                    '[name="mainFrame"]',
                    'iframe.mainFrame',
                ]

                # 方法1: 尝试通过选择器定位主内容iframe
                for selector in main_frame_selectors:
                    try:
                        frame_element = page.locator(selector)
                        if frame_element.count() > 0:
                            # 等待iframe加载
                            frame_element.wait_for(state='attached', timeout=5000)
                            # 获取frame对象
                            frame = page.frame(name='mainFrame') or page.frame(url=lambda u: 'mainFrame' in str(u) or '.html' in str(u))
                            if frame:
                                iframe_content = frame.content()
                                logger.info(f"[Axure解析] 通过选择器 {selector} 获取到mainFrame内容: {len(iframe_content)} 字符")
                                break
                    except Exception as e:
                        continue

                # 方法2: 遍历所有frames，查找包含实际内容的frame（排除导航frame）
                if not iframe_content or len(iframe_content) < 500:
                    logger.info("[Axure解析] 选择器方式未找到，尝试遍历所有frames...")
                    frames = page.frames
                    logger.info(f"[Axure解析] 共发现 {len(frames)} 个frames")

                    best_frame_content = ""
                    for i, frame in enumerate(frames):
                        try:
                            frame_url = frame.url
                            frame_name = frame.name
                            content = frame.content()
                            content_len = len(content)

                            logger.info(f"[Axure解析] Frame {i}: name={frame_name}, url={frame_url[:50] if frame_url else ''}..., 内容长度={content_len}")

                            # 跳过主frame和明显的导航frame
                            if frame == page.main_frame:
                                continue

                            # 跳过sitemap/导航相关的frame
                            frame_url_lower = frame_url.lower() if frame_url else ''
                            frame_name_lower = frame_name.lower() if frame_name else ''
                            if any(keyword in frame_url_lower or keyword in frame_name_lower
                                   for keyword in ['sitemap', 'toc', 'nav', 'menu', 'tree', 'left']):
                                logger.info(f"[Axure解析] 跳过导航frame: {frame_name}")
                                continue

                            # 选择内容最长的非导航frame
                            if content_len > len(best_frame_content):
                                best_frame_content = content
                                logger.info(f"[Axure解析] 更新最佳frame内容: {content_len} 字符")

                        except Exception as e:
                            logger.warning(f"[Axure解析] 获取frame {i} 内容失败: {e}")
                            continue

                    if best_frame_content:
                        iframe_content = best_frame_content

                # 方法3: 如果还是没有内容，获取整个页面
                if not iframe_content:
                    logger.info("[Axure解析] 未找到iframe，使用整页内容")
                    iframe_content = page.content()

                logger.info(f"[Axure解析] 最终获取内容长度: {len(iframe_content)}")

                # 保存target_frame用于后续获取computed color
                target_frame = page
                # 查找主内容frame
                for frame in page.frames:
                    frame_url = frame.url or ''
                    frame_name = frame.name or ''
                    # 跳过导航frame
                    if any(kw in frame_url.lower() or kw in frame_name.lower()
                           for kw in ['sitemap', 'toc', 'nav', 'menu', 'tree', 'left']):
                        continue
                    if frame != page.main_frame and len(frame_url) > 10:
                        target_frame = frame
                        break

                # 使用BeautifulSoup解析
                soup = BeautifulSoup(iframe_content, 'html.parser')

                full_texts = []
                incremental_texts = []
                tables_data = []

                # 移除脚本和样式
                for tag in soup(['script', 'style', 'noscript', 'link', 'meta']):
                    tag.decompose()

                # 过滤关键词 - Axure UI 界面元素
                axure_ui_keywords = [
                    # 基础UI
                    'preview', 'inspect', 'share', 'adaptive', 'comments', 'hotspots',
                    'collapse all', 'scale to', 'default scale', 'user scale',
                    'show note markers', 'copyright', 'axure', 'prototype',
                    'close', 'variables', 'zoom', 'pages', 'masters', 'console',
                    # Inspect 面板
                    'colors', 'assets', 'size and position', 'download all',
                    'copied to clipboard', 'typography', 'typeface', 'fill color',
                    'border', 'shadows', 'no notes for this page', 'add comment',
                    'mark all read', 'rotation', 'radius', 'padding', 'opacity',
                    'width:', 'height:', 'align:', 'position:', 'size:',
                    # 右侧面板
                    'add a comment', 'give feedback', 'ask a question', 'request a change',
                    # 其他
                    'sitemap', 'outline', 'notes', 'interactions', 'documentation',
                    'publish', 'generate', 'export', 'import', 'settings'
                ]

                # 完全匹配过滤（单独的短词）
                axure_exact_keywords = {'content', 'html', 'css', 'other'}

                code_keywords = [
                    'function(', 'var ', 'const ', 'let ', 'return ', 'console.',
                    'jquery', 'document.', 'window.', '$(', 'css(', 'axure.',
                    '{', '}', '===', '!=='
                ]

                def extract_text_smart(element):
                    text = element.get_text(strip=True)
                    if not text or len(text) < 2:
                        return None
                    text_lower = text.lower().strip()
                    # 完全匹配过滤
                    if text_lower in axure_exact_keywords:
                        return None
                    # 检查是否包含 Axure UI 关键词
                    if any(keyword in text_lower for keyword in axure_ui_keywords):
                        return None
                    if any(keyword in text for keyword in code_keywords):
                        return None
                    # 过滤纯数字
                    if text.isdigit():
                        return None
                    # 过滤类似 "X:" "Y:" "Width:" 等短标签
                    if len(text) <= 10 and text.endswith(':'):
                        return None
                    # 过滤组合标签如 "X:Y:" "Width:Height:"
                    if re.match(r'^[A-Za-z:]+$', text) and ':' in text:
                        return None
                    # 检查是否包含有效字符
                    if not any(c.isalpha() or c > '\u4e00' for c in text):
                        return None
                    if text.isascii() and len(text) < 3:
                        return None
                    # 过滤重复内容如 "×Colors" "×Assets"
                    if text.startswith('×'):
                        return None
                    return text

                def normalize_style(style_str):
                    """标准化样式字符串，去除所有空格并转小写"""
                    return style_str.lower().replace(' ', '').replace('\t', '').replace('\n', '')

                def check_color_in_style(style_str):
                    """检查样式字符串中是否包含蓝色/红色"""
                    normalized = normalize_style(style_str)
                    blue_patterns_normalized = [
                        'color:blue', 'color:#0000ff', 'color:#00f',
                        'color:rgb(0,0,255)', 'color:#0066cc', 'color:#0066ff',
                        'color:#3366ff', 'color:#1e90ff', 'color:#4169e1',
                        'color:#0000cd', 'color:#000080', 'color:#0080ff',
                        'color:#4a90e2', 'color:#5b9bd5', 'color:#2196f3',
                        'color:#1976d2', 'color:dodgerblue', 'color:royalblue',
                        'color:steelblue', 'color:cornflowerblue',
                        'color:red', 'color:#ff0000', 'color:#f00',
                        'color:rgb(255,0,0)', 'color:#dc143c', 'color:#ff4500',
                        'color:#ff6347', 'color:#b22222', 'color:#8b0000',
                        'color:#cc0000', 'color:crimson', 'color:darkred',
                        'color:firebrick',
                    ]
                    for pattern in blue_patterns_normalized:
                        if pattern in normalized:
                            return True
                    # 使用正则匹配 rgb 格式
                    if re.search(r'color[:\s]*rgb\s*\(\s*0\s*,\s*0\s*,\s*255\s*\)', style_str, re.IGNORECASE):
                        return True
                    if re.search(r'color[:\s]*rgb\s*\(\s*255\s*,\s*0\s*,\s*0\s*\)', style_str, re.IGNORECASE):
                        return True
                    return False

                def check_element_color(element):
                    """检查元素及其祖先是否有蓝色/红色样式"""
                    # 检查元素自身
                    style = element.get('style', '')
                    if style and check_color_in_style(style):
                        return True
                    # 检查父元素（最多5层）
                    parent = element.parent
                    for _ in range(5):
                        if parent is None or parent.name is None:
                            break
                        parent_style = parent.get('style', '')
                        if parent_style and check_color_in_style(parent_style):
                            return True
                        parent = parent.parent
                    return False

                def check_cell_has_blue_color(td_element):
                    """检查单元格内是否有蓝色/红色内容（包括子元素）"""
                    # 检查单元格自身
                    if check_element_color(td_element):
                        return True
                    # 检查单元格内的所有子元素
                    for child in td_element.find_all(recursive=True):
                        if check_element_color(child):
                            return True
                    return False

                # ============= 使用JavaScript获取computed color =============
                # 这是关键修复：Axure渲染后的蓝色是通过CSS设置的，不是inline style
                # 所以需要用JavaScript获取computedStyle.color
                # 注意：这段代码必须在browser.close()之前执行
                blue_texts_from_js = set()
                try:
                    logger.info("[Axure解析] 使用JavaScript获取computed color...")
                    color_info = target_frame.evaluate("""
                    () => {
                        const results = [];
                        const elements = document.querySelectorAll('div, span, p, h1, h2, h3, h4, h5, h6, li, a, td, th, label');
                        for (const el of elements) {
                            const text = el.innerText ? el.innerText.trim() : '';
                            if (text && text.length > 1 && text.length < 500) {
                                const style = window.getComputedStyle(el);
                                const color = style.color;
                                results.push({
                                    text: text.substring(0, 200),
                                    color: color
                                });
                            }
                        }
                        return results;
                    }
                    """)

                    if color_info:
                        for info in color_info:
                            color = info.get('color', '')
                            text = info.get('text', '').strip()
                            if not text or not color:
                                continue
                            # 检查是否是蓝色系或红色系
                            is_blue = False
                            if 'rgb' in color:
                                try:
                                    parts = color.replace('rgb(', '').replace('rgba(', '').replace(')', '').split(',')
                                    r, g, b = int(parts[0].strip()), int(parts[1].strip()), int(parts[2].strip())
                                    # 蓝色: B高(>150), R低(<150)
                                    if b > 150 and r < 150:
                                        is_blue = True
                                    # 红色: R高(>200), G和B低(<100)
                                    elif r > 200 and g < 100 and b < 100:
                                        is_blue = True
                                except:
                                    pass
                            if is_blue:
                                blue_texts_from_js.add(text)
                                # 也添加文本的子串（因为元素可能嵌套，导致文本重复）
                                for line in text.split('\n'):
                                    line = line.strip()
                                    if line and len(line) > 1:
                                        blue_texts_from_js.add(line)

                    logger.info(f"[Axure解析] JavaScript识别到 {len(blue_texts_from_js)} 条蓝色/红色文本")
                except Exception as js_err:
                    logger.warning(f"[Axure解析] JavaScript获取computed color失败: {js_err}")

                def is_text_blue_by_js(text):
                    """检查文本是否被JavaScript识别为蓝色"""
                    if not text:
                        return False
                    text = text.strip()
                    # 精确匹配
                    if text in blue_texts_from_js:
                        return True
                    # 检查文本是否是某个蓝色文本的子串（文本被包含在蓝色文本中）
                    for blue_text in blue_texts_from_js:
                        if text in blue_text:
                            return True
                    return False

                # ============= JavaScript computed color 检测结束 =============

                # 提取表格数据 - 同时检测蓝色行
                incremental_table_rows = []  # 存储包含蓝色内容的表格行
                table_headers = []  # 存储表头

                for table in soup.find_all('table'):
                    rows = []
                    current_header = []
                    for row_idx, tr in enumerate(table.find_all('tr')):
                        cells = []
                        row_has_blue = False  # 标记该行是否有蓝色内容

                        for td in tr.find_all(['td', 'th']):
                            cell_text = td.get_text(strip=True)
                            cell_text = ' '.join(cell_text.split())  # 清理空白
                            cells.append(cell_text)

                            # 检查该单元格是否有蓝色/红色内容
                            # 方法1: 检查inline style（原有逻辑）
                            if check_cell_has_blue_color(td):
                                row_has_blue = True
                            # 方法2: 检查JavaScript computed color（新增逻辑）
                            elif is_text_blue_by_js(cell_text):
                                row_has_blue = True

                        if cells and any(c for c in cells):
                            rows.append(cells)

                            # 第一行通常是表头
                            if row_idx == 0:
                                current_header = cells
                            elif row_has_blue and current_header:
                                # 如果该行有蓝色内容，记录整行（带表头信息）
                                incremental_table_rows.append({
                                    'header': current_header,
                                    'row': cells
                                })

                    if rows:
                        tables_data.append(rows)
                        if current_header:
                            table_headers.append(current_header)

                # 提取非表格的文本元素
                seen_texts = set()

                for element in soup.find_all(['div', 'span', 'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'a']):
                    # 跳过表格内的元素（已单独处理）
                    if element.find_parent('table'):
                        continue

                    text = extract_text_smart(element)
                    if not text:
                        continue

                    # 检查是否是增量内容（蓝色/红色）
                    # 方法1: 检查inline style（原有逻辑）
                    is_increment = check_element_color(element)
                    # 方法2: 检查JavaScript computed color（新增逻辑，修复CSS设置颜色的情况）
                    if not is_increment:
                        is_increment = is_text_blue_by_js(text)

                    # 增量内容：即使文本重复也要记录
                    if is_increment and text not in incremental_texts:
                        incremental_texts.append(text)

                    # 全量内容：去重
                    if text not in seen_texts:
                        seen_texts.add(text)
                        full_texts.append(text)

                browser.close()

                # 构建 Markdown 输出 - 全量内容
                md_parts = []

                if page_name:
                    md_parts.append(f"# {page_name}\n")

                if tables_data:
                    for idx, table_rows in enumerate(tables_data):
                        if len(table_rows) > 1:
                            max_cols = max(len(row) for row in table_rows)
                            md_parts.append(f"\n## 表格 {idx + 1}\n")
                            header = table_rows[0] if table_rows else []
                            header_padded = header + [''] * (max_cols - len(header))
                            md_parts.append("| " + " | ".join(header_padded) + " |")
                            md_parts.append("| " + " | ".join(['---'] * max_cols) + " |")
                            for row in table_rows[1:]:
                                row_padded = row + [''] * (max_cols - len(row))
                                row_cleaned = [cell.replace('\n', ' ').replace('\r', '').replace('|', '｜') for cell in row_padded]
                                md_parts.append("| " + " | ".join(row_cleaned) + " |")
                            md_parts.append("")

                if full_texts:
                    md_parts.append("\n## 页面内容\n")
                    for text in full_texts[:200]:
                        if len(text) <= 50 and re.search(r'[：:](|页面|功能|模块|流程|说明|规则|字段|管理|配置)$', text):
                            md_parts.append(f"\n### {text}\n")
                        else:
                            md_parts.append(f"- {text}")

                full_content = "\n".join(md_parts)
                full_content = re.sub(r'\n{3,}', '\n\n', full_content)

                # 构建增量内容 - 包含蓝色表格行和蓝色文本
                inc_parts = []

                # 1. 先输出包含蓝色内容的表格行（以完整表格格式）
                if incremental_table_rows:
                    inc_parts.append("# 增量需求（蓝色/红色标记内容）\n")
                    inc_parts.append("## 增量表格字段\n")

                    # 按表头分组显示
                    header_groups = {}
                    for item in incremental_table_rows:
                        header_key = tuple(item['header'])
                        if header_key not in header_groups:
                            header_groups[header_key] = []
                        header_groups[header_key].append(item['row'])

                    for header, rows in header_groups.items():
                        header_list = list(header)
                        max_cols = max(len(header_list), max(len(row) for row in rows))

                        # 输出表头
                        header_padded = header_list + [''] * (max_cols - len(header_list))
                        inc_parts.append("| " + " | ".join(header_padded) + " |")
                        inc_parts.append("| " + " | ".join(['---'] * max_cols) + " |")

                        # 输出蓝色行
                        for row in rows:
                            row_padded = row + [''] * (max_cols - len(row))
                            row_cleaned = [cell.replace('\n', ' ').replace('\r', '').replace('|', '｜') for cell in row_padded]
                            inc_parts.append("| " + " | ".join(row_cleaned) + " |")

                        inc_parts.append("")  # 表格间空行

                # 2. 再输出非表格的蓝色文本
                if incremental_texts:
                    if not inc_parts:
                        inc_parts.append("# 增量需求（蓝色/红色标记内容）\n")
                    if incremental_table_rows:
                        inc_parts.append("## 其他增量内容\n")
                    for text in incremental_texts:
                        inc_parts.append(f"- {text}")

                incremental_content = "\n".join(inc_parts) if inc_parts else ""

                logger.info(f"提取完成: 全量内容 {len(full_content)} 字符, 增量内容 {len(incremental_content)} 字符")
                logger.info(f"提取了 {len(tables_data)} 个表格, {len(full_texts)} 条文本, {len(incremental_table_rows)} 条增量表格行")

                # ============= 检测流程图 =============
                flowchart_data = detect_and_extract_flowchart(soup, iframe_content)
                if flowchart_data.get('has_flowchart'):
                    logger.info(f"[流程图检测] 检测到流程图，共 {len(flowchart_data.get('nodes', []))} 个节点")

                return {
                    'success': True,
                    'message': '成功获取Axure内容',
                    'full_content': full_content.strip(),
                    'incremental_content': incremental_content.strip(),
                    'page_title': page_name or "需求页面",
                    'flowchart_data': flowchart_data  # 包含流程图检测结果
                }

        except ImportError as e:
            logger.error(f"playwright库未安装: {e}")
            return {
                'success': False,
                'message': f'playwright库未安装，请先运行: pip install playwright && playwright install chromium',
                'full_content': '',
                'incremental_content': ''
            }
        except Exception as e:
            logger.error(f"获取Axure内容失败: {e}")
            traceback.print_exc()
            return {
                'success': False,
                'message': f'获取失败: {str(e)}',
                'full_content': '',
                'incremental_content': ''
            }

    def _handle_login(self, page):
        """处理登录页面"""
        try:
            page_title = page.title()
            if '认证' in page_title or 'login' in page_title.lower():
                logger.info("检测到登录页面，正在登录...")
                try:
                    login_methods = [
                        ('input[placeholder="请输入您的用户名"]', 'input[placeholder="请输入您的密码"]'),
                        ('input[name="username"]', 'input[name="password"]'),
                        ('input[type="text"]', 'input[type="password"]'),
                    ]

                    for user_sel, pwd_sel in login_methods:
                        try:
                            if page.locator(user_sel).count() > 0:
                                page.locator(user_sel).fill(self.username)
                                page.locator(pwd_sel).fill(self.password)
                                break
                        except Exception:
                            continue

                    login_btns = ['button:has-text("登录")', 'input[type="submit"]', 'button[type="submit"]']
                    for btn_sel in login_btns:
                        try:
                            if page.locator(btn_sel).count() > 0:
                                page.locator(btn_sel).click()
                                break
                        except Exception:
                            continue

                    page.wait_for_load_state('networkidle')
                    time.sleep(3)
                    logger.info("登录成功")
                except Exception as login_error:
                    logger.warning(f"登录处理警告: {login_error}")

        except Exception as e:
            logger.warning(f"登录处理异常: {e}")

    @staticmethod
    def format_axure_text_to_markdown(axure_text: str) -> str:
        """
        将 Axure 提取的文本转换为 Markdown 格式
        """
        if not axure_text:
            return ""

        lines = [l.strip() for l in axure_text.split("\n") if l and l.strip()]
        md_lines = ["# 原型需求提取\n"]
        last_was_heading = False

        for line in lines:
            # 标题判断：短且包含关键词
            if (len(line) <= 40 and
                re.search(r"[：:]|(页面|功能|模块|流程|用例|说明|规则|字段)$", line) or
                    (line.istitle() and not re.search(r"\s", line) and len(line) <= 20)):
                if not last_was_heading:
                    md_lines.append("")
                md_lines.append(f"## {line}")
                last_was_heading = True
            else:
                # 转换为列表项
                bullet = line
                kv = re.split(r"[：:]", line, maxsplit=1)
                if len(kv) == 2 and len(kv[0]) <= 20:
                    bullet = f"**{kv[0].strip()}**: {kv[1].strip()}"
                md_lines.append(f"- {bullet}")
                last_was_heading = False

        return "\n".join(md_lines).strip()

    @staticmethod
    def format_incremental_text_to_markdown(incremental_text: str) -> str:
        """
        将增量内容（蓝色文本）转换为 Markdown 格式
        """
        if not incremental_text:
            return ""

        lines = [l.strip() for l in incremental_text.split("\n") if l and l.strip()]
        if not lines:
            return ""

        md_lines = ["# 增量需求提取\n"]
        md_lines.append("> 以下内容为原型中的蓝色字体部分，通常表示新增或修改的需求\n\n")

        for line in lines:
            if (len(line) <= 50 and
                (re.search(r"[：:]|(新增|修改|更新|优化|改进|功能|模块|页面|流程)$", line) or
                    line.istitle() and len(line) <= 30)):
                md_lines.append(f"## {line}")
            else:
                md_lines.append(f"- {line}")

        return "\n".join(md_lines).strip()

    async def fetch_axure_content_async(self, url: str, wait_time: int = 5) -> Dict[str, str]:
        """异步版本：使用线程池运行同步版本"""
        func = lambda: self.fetch_axure_content(url, wait_time)
        result = await asyncio.to_thread(func)
        return result


# ==================== 流程图检测与转换 ====================

def detect_and_extract_flowchart(soup, iframe_content: str) -> Dict:
    """
    检测并提取Axure页面中的流程图元素

    Args:
        soup: BeautifulSoup对象
        iframe_content: 原始HTML内容

    Returns:
        Dict包含:
        - has_flowchart: 是否检测到流程图
        - nodes: 节点列表 [{text, x, y, width, height, shape_type}]
        - connections: 连接信息
        - description: 流程图的文字描述
    """
    result = {
        'has_flowchart': False,
        'nodes': [],
        'connections': [],
        'description': ''
    }

    # 检测流程图的特征
    # 1. Axure 使用 img 标签引用外部 SVG 作为连接线/箭头
    has_connector_images = False
    connector_count = 0

    for img in soup.find_all('img'):
        src = img.get('src', '')
        img_id = img.get('id', '')
        # 检测连接线图片: _seg 模式 或 arrow/connector 相关
        if ('_seg' in src.lower() or '_seg' in img_id.lower() or
            'arrow' in src.lower() or 'connector' in src.lower() or
            (src.endswith('.svg') and 'images' in src)):
            connector_count += 1
            if connector_count >= 2:  # 至少2个连接线
                has_connector_images = True

    # 2. 也检查内嵌 SVG 元素（备用）
    svg_elements = soup.find_all('svg')
    has_svg_lines = False
    for svg in svg_elements:
        if svg.find_all(['path', 'line', 'polyline']):
            has_svg_lines = True
            break

    # 3. 检测带有位置信息的形状元素
    positioned_elements = []
    flowchart_keywords = ['开始', '结束', '判断', '是', '否', 'yes', 'no', 'start', 'end',
                          '流程', '步骤', '条件', '分支', '循环', '处理', '输入', '输出',
                          '提交', '审核', '审批', '通过', '拒绝', '完成', '发起', '申请']

    # 查找所有绝对定位的div元素
    for div in soup.find_all('div', style=True):
        style = div.get('style', '')
        # 检查是否是绝对定位且有位置信息
        if 'position' in style.lower() and ('left' in style.lower() or 'top' in style.lower()):
            text = div.get_text(strip=True)
            if text and len(text) < 100:  # 流程图节点文字通常较短
                # 解析位置信息
                left_match = re.search(r'left:\s*(-?\d+(?:\.\d+)?)\s*px', style, re.IGNORECASE)
                top_match = re.search(r'top:\s*(-?\d+(?:\.\d+)?)\s*px', style, re.IGNORECASE)
                width_match = re.search(r'width:\s*(-?\d+(?:\.\d+)?)\s*px', style, re.IGNORECASE)
                height_match = re.search(r'height:\s*(-?\d+(?:\.\d+)?)\s*px', style, re.IGNORECASE)

                if left_match and top_match:
                    node = {
                        'text': text,
                        'x': float(left_match.group(1)),
                        'y': float(top_match.group(1)),
                        'width': float(width_match.group(1)) if width_match else 100,
                        'height': float(height_match.group(1)) if height_match else 50,
                        'shape_type': 'process'  # 默认为处理框
                    }

                    # 根据关键词判断形状类型
                    text_lower = text.lower()
                    if any(k in text_lower for k in ['开始', 'start', '起始', '发起']):
                        node['shape_type'] = 'start'
                    elif any(k in text_lower for k in ['结束', 'end', '完成', '终止']):
                        node['shape_type'] = 'end'
                    elif any(k in text_lower for k in ['判断', '条件', '是否', '?', '？', '审核', '审批']):
                        node['shape_type'] = 'decision'
                    elif text in ['是', '否', 'yes', 'no', 'Y', 'N', '通过', '拒绝', '同意', '不同意']:
                        node['shape_type'] = 'label'  # 连接线上的标签

                    positioned_elements.append(node)

    # 判断是否是流程图
    # 条件：有多个定位元素 + (有连接线图片 或 有SVG连接线 或 有流程图关键词)
    has_flowchart_keywords = any(
        any(kw in node['text'].lower() for kw in flowchart_keywords)
        for node in positioned_elements
    )

    if len(positioned_elements) >= 3 and (has_connector_images or has_svg_lines or has_flowchart_keywords):
        result['has_flowchart'] = True
        result['nodes'] = positioned_elements
        result['connector_count'] = connector_count

        # 按位置排序（先上后下，先左后右）
        sorted_nodes = sorted(positioned_elements, key=lambda n: (n['y'], n['x']))

        # 生成描述
        descriptions = []
        for i, node in enumerate(sorted_nodes):
            if node['shape_type'] != 'label':
                descriptions.append(f"{i+1}. [{node['shape_type']}] {node['text']}")

        result['description'] = '\n'.join(descriptions)
        logger.info(f"[流程图检测] 检测到 {len(positioned_elements)} 个节点, {connector_count} 个连接线图片")

    return result


async def convert_flowchart_to_mermaid_async(flowchart_data: Dict, api_key: str = None, base_url: str = None,
                                              model_name: str = None) -> str:
    """
    调用AI将流程图描述转换为Mermaid代码（异步版本）

    Args:
        flowchart_data: detect_and_extract_flowchart返回的数据
        api_key: API Key
        base_url: API Base URL
        model_name: 模型名称

    Returns:
        Mermaid格式的流程图代码
    """
    import httpx

    if not flowchart_data.get('has_flowchart') or not flowchart_data.get('nodes'):
        return ""

    # 从配置获取默认值
    from backend.config_loader import config_loader
    if not api_key:
        api_key = config_loader.get('LLM.QWEN_API_KEY', '')
    if not base_url:
        base_url = config_loader.get('LLM.QWEN_BASE_URL', '')
    if not model_name:
        model_name = config_loader.get('LLM.REFINER_MODEL', 'qwen-plus')

    if not api_key or not base_url:
        logger.warning("[流程图转换] 未配置 LLM API Key 或 Base URL")
        return ""

    # 构建提示词
    nodes_desc = []
    for node in flowchart_data['nodes']:
        if node['shape_type'] != 'label':
            nodes_desc.append(f"- 类型:{node['shape_type']}, 文字:「{node['text']}」, 位置:(x={node['x']}, y={node['y']})")

    labels = [n for n in flowchart_data['nodes'] if n['shape_type'] == 'label']
    labels_desc = ', '.join([f"「{l['text']}」" for l in labels]) if labels else "无"

    prompt = f"""请根据以下从Axure原型中提取的流程图元素，生成Mermaid格式的流程图代码。

## 提取的节点信息（按位置排序，y值越小越靠上）:
{chr(10).join(nodes_desc)}

## 连接线上的标签文字:
{labels_desc}

## 要求:
1. 使用 flowchart TD（从上到下）或 flowchart LR（从左到右）格式
2. 根据节点的位置关系（y值）推断连接顺序
3. 开始节点使用圆角矩形 ([文字])
4. 结束节点使用圆角矩形 ([文字])
5. 判断/条件节点使用菱形 {{文字}}
6. 普通处理节点使用矩形 [文字]
7. 如果有"是/否"等标签，添加到连接线上
8. 只输出Mermaid代码，不要其他解释

## 示例输出格式:
```mermaid
flowchart TD
    A([开始]) --> B[处理步骤1]
    B --> C{{判断条件}}
    C -->|是| D[处理步骤2]
    C -->|否| E[处理步骤3]
    D --> F([结束])
    E --> F
```

请生成Mermaid代码:"""

    try:
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }

        api_url = base_url.rstrip('/')
        if not api_url.endswith('/chat/completions'):
            api_url = f"{api_url}/chat/completions"

        data = {
            'model': model_name,
            'messages': [
                {"role": "user", "content": prompt}
            ],
            'max_tokens': 2048,
            'temperature': 0.3,
            'stream': False
        }

        logger.info(f"[流程图转换] 开始调用 LLM API, model={model_name}")

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(api_url, headers=headers, json=data)

            if response.status_code == 200:
                result = response.json()
                content = result.get('choices', [{}])[0].get('message', {}).get('content', '')

                if not content:
                    return ""

                # 提取代码块中的内容
                if '```mermaid' in content:
                    match = re.search(r'```mermaid\s*([\s\S]*?)\s*```', content)
                    if match:
                        return match.group(1).strip()
                elif '```' in content:
                    match = re.search(r'```\s*([\s\S]*?)\s*```', content)
                    if match:
                        return match.group(1).strip()

                # 如果没有代码块，检查是否直接返回了flowchart代码
                if content.strip().startswith('flowchart'):
                    return content.strip()

                return ""
            else:
                logger.warning(f"[流程图转换] API调用失败: {response.status_code}")
                return ""

    except Exception as e:
        logger.error(f"[流程图转换] AI转换失败: {e}")
        return ""


# 创建全局服务实例
axure_service = AxureService()


def refine_requirements_markdown(requirement_text: str, api_key: str = None, base_url: str = None,
                                  model_name: str = None, max_tokens: int = 4096,
                                  temperature: float = 0.3) -> str:
    """
    使用 LLM 对需求文本进行结构化整理
    """
    import httpx

    # 从数据库或配置获取默认值
    from apps.knowledge_base.models import KnowledgeBaseConfig
    db_config = KnowledgeBaseConfig.objects.filter(is_active=True).first()
    
    if not api_key:
        api_key = db_config.refiner_api_key if db_config else None
    if not base_url:
        base_url = db_config.refiner_base_url if db_config else None
    if not model_name:
        model_name = db_config.refiner_model if db_config and db_config.refiner_model else 'qwen-plus'

    if not api_key or not base_url:
        from backend.config_loader import config_loader
        api_key = api_key or config_loader.get('LLM.QWEN_API_KEY', '')
        base_url = base_url or config_loader.get('LLM.QWEN_BASE_URL', '')
        model_name = model_name or config_loader.get('LLM.REFINER_MODEL', 'qwen-plus')

    if not api_key or not base_url:
        logger.warning("未配置 LLM API Key 或 Base URL，返回原始文本")
        return requirement_text

    prompt = f"""
你是一名文档整理专家。请将以下从原型提取的文字整理为清晰的Markdown格式，要求：

1. **保持原型的原始结构和层级关系**，不要改变内容的组织方式，去掉菜单功能描述，只保留页面主要功能描述和介绍

2. **表格处理（重要）**：
   - 如果内容包含表格数据，必须转换为标准 Markdown 表格格式
   - 标准格式示例：
     ```
     | 列1 | 列2 | 列3 |
     |-----|-----|-----|
     | 数据1 | 数据2 | 数据3 |
     ```
   - 确保每行的列数一致，表头和分隔符完整
   - 识别"字段|类型|说明"等结构并格式化为表格

3. **流程图处理（重要）**：
   - 如果内容描述了流程、步骤、状态转换，请用 Mermaid 流程图格式输出
   - 格式示例：
     ```mermaid
     flowchart TD
         A[开始] --> B{{判断条件}}
         B -->|是| C[执行操作1]
         B -->|否| D[执行操作2]
         C --> E[结束]
         D --> E
     ```

4. 使用合适的Markdown标记：
   - 标题用 # ## ###
   - 列表用 - 或 1. 2. 3.
   - 重要内容可以用 **加粗**
   - 代码或技术术语用 `反引号`

5. 清理格式问题：
   - 去除多余的空行和空格
   - 修复破碎的句子
   - 合并重复的内容
   - 不要删除原有内容

6. **不要添加原文没有的内容**，不要臆造字段或功能

待整理内容：
{requirement_text}
"""

    try:
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }

        api_url = base_url.rstrip('/')
        if not api_url.endswith('/chat/completions'):
            api_url = f"{api_url}/chat/completions"

        data = {
            'model': model_name,
            'messages': [
                {"role": "user", "content": prompt}
            ],
            'max_tokens': max_tokens,
            'temperature': temperature,
            'stream': False
        }

        logger.info(f"开始调用 LLM API 进行结构化整理, model={model_name}")

        with httpx.Client(timeout=120.0) as client:
            response = client.post(api_url, headers=headers, json=data)

            if response.status_code == 200:
                result = response.json()
                content = result.get('choices', [{}])[0].get('message', {}).get('content', '')
                if content:
                    logger.info(f"AI 结构化整理完成, 结果长度: {len(content)}")
                    return content.strip()
                else:
                    logger.warning("LLM 返回内容为空，使用原始文本")
                    return requirement_text
            else:
                logger.warning(f"LLM API 调用失败: {response.status_code} - {response.text}")
                return requirement_text

    except Exception as e:
        logger.error(f"AI 结构化整理失败: {e}")
        return requirement_text


async def refine_requirements_markdown_async(requirement_text: str, api_key: str = None, base_url: str = None,
                                              model_name: str = None, max_tokens: int = 4096,
                                              temperature: float = 0.3) -> str:
    """
    异步版本：使用 LLM 对需求文本进行结构化整理
    """
    import httpx

    # 从数据库或配置获取默认值
    from apps.knowledge_base.models import KnowledgeBaseConfig
    db_config = await KnowledgeBaseConfig.objects.filter(is_active=True).afirst()
    
    if not api_key:
        api_key = db_config.refiner_api_key if db_config else None
    if not base_url:
        base_url = db_config.refiner_base_url if db_config else None
    if not model_name:
        model_name = db_config.refiner_model if db_config and db_config.refiner_model else 'qwen-plus'

    if not api_key or not base_url:
        from backend.config_loader import config_loader
        api_key = api_key or config_loader.get('LLM.QWEN_API_KEY', '')
        base_url = base_url or config_loader.get('LLM.QWEN_BASE_URL', '')
        model_name = model_name or config_loader.get('LLM.REFINER_MODEL', 'qwen-plus')

    if not api_key or not base_url:
        logger.warning("未配置 LLM API Key 或 Base URL，返回原始文本")
        return requirement_text

    prompt = f"""
你是一名文档整理专家。请将以下从原型提取的文字整理为清晰的Markdown格式，要求：

1. **保持原型的原始结构和层级关系**，不要改变内容的组织方式，去掉菜单功能描述，只保留页面主要功能描述和介绍

2. **表格处理（重要）**：
   - 如果内容包含表格数据，必须转换为标准 Markdown 表格格式
   - 标准格式示例：
     ```
     | 列1 | 列2 | 列3 |
     |-----|-----|-----|
     | 数据1 | 数据2 | 数据3 |
     ```
   - 确保每行的列数一致，表头和分隔符完整
   - 识别"字段|类型|说明"等结构并格式化为表格

3. **流程图处理（重要）**：
   - 如果内容描述了流程、步骤、状态转换，请用 Mermaid 流程图格式输出
   - 格式示例：
     ```mermaid
     flowchart TD
         A[开始] --> B{{判断条件}}
         B -->|是| C[执行操作1]
         B -->|否| D[执行操作2]
         C --> E[结束]
         D --> E
     ```

4. 使用合适的Markdown标记：
   - 标题用 # ## ###
   - 列表用 - 或 1. 2. 3.
   - 重要内容可以用 **加粗**
   - 代码或技术术语用 `反引号`

5. 清理格式问题：
   - 去除多余的空行和空格
   - 修复破碎的句子
   - 合并重复的内容
   - 不要删除原有内容

6. **不要添加原文没有的内容**，不要臆造字段或功能

待整理内容：
{requirement_text}
"""

    try:
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }

        api_url = base_url.rstrip('/')
        if not api_url.endswith('/chat/completions'):
            api_url = f"{api_url}/chat/completions"

        data = {
            'model': model_name,
            'messages': [
                {"role": "user", "content": prompt}
            ],
            'max_tokens': max_tokens,
            'temperature': temperature,
            'stream': False
        }

        logger.info(f"[异步] 开始调用 LLM API 进行结构化整理, model={model_name}")

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(api_url, headers=headers, json=data)

            if response.status_code == 200:
                result = response.json()
                content = result.get('choices', [{}])[0].get('message', {}).get('content', '')
                if content:
                    logger.info(f"[异步] AI 结构化整理完成, 结果长度: {len(content)}")
                    return content.strip()
                else:
                    logger.warning("[异步] LLM 返回内容为空，使用原始文本")
                    return requirement_text
            else:
                logger.warning(f"[异步] LLM API 调用失败: {response.status_code} - {response.text}")
                return requirement_text

    except Exception as e:
        logger.error(f"[异步] AI 结构化整理失败: {e}")
        return requirement_text
