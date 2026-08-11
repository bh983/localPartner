import os
import sys
import re
import json
import socket
import urllib.parse
import urllib.request
import urllib.error
import mimetypes
import traceback
import threading
import io

import wx
import wx.adv
import wx.xml
import wx.lib.scrolledpanel as scrolled
import wx.richtext as rt

# 尝试导入 anitopy 依赖库
try:
    import anitopy
except ImportError:
    wx.MessageBox("缺失 anitopy 依赖库！\n请在终端运行：pip install anitopy", "错误", wx.OK | wx.ICON_ERROR)
    sys.exit(1)

# ==================== 基本配置 ====================
APP_NAME = "localPartner"
APP_VERSION = "105"
DEVELOPER_NAME = "983"
DEFAULT_PORT = 8080
SUPPORTED_EXTS = {'.mkv', '.mp4', '.avi', '.flv', '.mov', '.webm', '.ts', '.m4v'}

# 全局网络海报内存缓存
POSTER_CACHE = {}


# ==================== PyInstaller 资源路径兼容 ====================
def resource_path(relative_path):
    """获取资源的绝对路径，兼容 PyInstaller 单文件打包 (_MEIPASS)"""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


# ==================== 辅助工具函数 ====================
def get_local_ip():
    """获取本机局域网 IP 地址"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def fallback_extract_episode(filename):
    """正则降级匹配提取集数"""
    matches = re.findall(r'\[(\d+(?:\.\d+)?)\]', filename)
    if not matches:
        matches = re.findall(r'(?:[eE][pP]|\s-\s|第)(\d+(?:\.\d+)?)', filename)
    if not matches:
        return "01"
    ignored = {'1080', '720', '480', '2160', '4k', '2020', '2021', '2022', '2023', '2024', '2025', '2026'}
    valid_matches = [m for m in matches if m not in ignored]
    return valid_matches[-1] if valid_matches else matches[0]


def ep_sort_key(ep_str):
    """自然排序键值计算"""
    try:
        return (0, float(ep_str))
    except ValueError:
        return (1, str(ep_str))


# ==================== 在线 API 接口逻辑 ====================
def fetch_moegirl_info_online(keyword, timeout=4):
    """使用萌娘百科 (MediaWiki API) 检索动画条目名称与封面"""
    if not keyword or not keyword.strip():
        return None, None, None, False

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) localPartner/105"
    }

    try:
        encoded_kw = urllib.parse.quote(keyword)
        url = (f"https://zh.moegirl.org.cn/api.php?action=query&generator=search"
               f"&gsrsearch={encoded_kw}&gsrlimit=1&prop=pageimages|info"
               f"&pithumbsize=300&format=json&utf8=1")
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            res_json = json.loads(resp.read().decode('utf-8'))
            pages = res_json.get('query', {}).get('pages', {})
            if pages:
                page = list(pages.values())[0]
                page_id = str(page.get('pageid', ''))
                title = page.get('title', '')
                thumbnail = page.get('thumbnail', {})
                cover_url = thumbnail.get('source', None)
                return title, page_id, cover_url, False
    except (socket.timeout, urllib.error.URLError) as e:
        is_timeout = isinstance(e, socket.timeout) or (hasattr(e, 'reason') and isinstance(e.reason, socket.timeout))
        return None, None, None, is_timeout
    except Exception:
        pass

    return None, None, None, False


def fetch_bangumi_info_online(keyword, timeout=4):
    """使用 Bangumi API 在线获取番剧中文译名、ID 与海报 URL"""
    if not keyword or not keyword.strip():
        return None, None, None, False

    headers = {
        "User-Agent": "localPartner/105 (https://github.com/)",
        "Content-Type": "application/json"
    }

    try:
        url_v0 = "https://api.bgm.tv/v0/search/subjects"
        body = json.dumps({
            "keyword": keyword,
            "filter": {"type": [2]}
        }).encode('utf-8')
        req = urllib.request.Request(url_v0, data=body, headers=headers, method='POST')
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            res_json = json.loads(resp.read().decode('utf-8'))
            data = res_json.get('data', [])
            if data:
                item = data[0]
                bgm_id = str(item.get('id'))
                name_cn = item.get('name_cn') or item.get('name')
                images = item.get('images', {})
                cover_url = images.get('common') or images.get('medium') or images.get('small')
                return name_cn, bgm_id, cover_url, False
    except (socket.timeout, urllib.error.URLError) as e:
        is_timeout = isinstance(e, socket.timeout) or (hasattr(e, 'reason') and isinstance(e.reason, socket.timeout))
        return None, None, None, is_timeout
    except Exception:
        pass

    return None, None, None, False


def download_image_as_bitmap(url, target_size=(70, 100)):
    """下载图片并缩放为 wx.Bitmap"""
    if not url:
        return None
    if url in POSTER_CACHE:
        return POSTER_CACHE[url]

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            img_data = resp.read()
            stream = io.BytesIO(img_data)
            image = wx.Image(stream)
            if image.IsOk():
                image = image.Scale(target_size[0], target_size[1], wx.IMAGE_QUALITY_HIGH)
                bmp = wx.Bitmap(image)
                POSTER_CACHE[url] = bmp
                return bmp
    except Exception:
        pass
    return None


def create_placeholder_bitmap(size=(70, 100), text="无海报"):
    """动态绘制极组占位图"""
    bmp = wx.Bitmap(size[0], size[1])
    dc = wx.MemoryDC()
    dc.SelectObject(bmp)
    dc.SetBackground(wx.Brush(wx.SystemSettings.GetColour(wx.SYS_COLOUR_BTNFACE)))
    dc.Clear()
    dc.SetPen(wx.Pen(wx.SystemSettings.GetColour(wx.SYS_COLOUR_GRAYTEXT), 1))
    dc.DrawRectangle(0, 0, size[0], size[1])

    font = wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT)
    font.SetPointSize(8)
    dc.SetFont(font)
    dc.SetTextForeground(wx.SystemSettings.GetColour(wx.SYS_COLOUR_GRAYTEXT))

    tw, th = dc.GetTextExtent(text)
    dc.DrawText(text, (size[0] - tw) // 2, (size[1] - th) // 2)
    dc.SelectObject(wx.NullBitmap)
    return bmp


# ==================== 后端 HTTP 服务端 ====================
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn


class ThreadedHTTPServer6(ThreadingMixIn, HTTPServer):
    address_family = socket.AF_INET6
    daemon_threads = True

    def server_bind(self):
        # 显式取消 IPV6_V6ONLY 限制，开启 IPv4/IPv6 双栈监听（Windows 默认可能已开启，这样写更稳妥）
        try:
            self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        except Exception:
            pass
        super().server_bind()

class KazumiRequestHandler(BaseHTTPRequestHandler):
    library_data = []
    allowed_dirs = []
    logger_callback = None

    def log_message(self, format, *args):
        pass

    def log_custom(self, code, msg=""):
        client_ip = self.client_address[0]
        parsed = urllib.parse.urlparse(self.path)
        full_query = f"?{parsed.query}" if parsed.query else ""
        decoded_path = urllib.parse.unquote(f"{parsed.path}{full_query}")

        if len(decoded_path) > 42:
            short_path = decoded_path[:39] + "..."
        else:
            short_path = decoded_path

        log_str = f"[{code}] {client_ip} -> {short_path:<42} | {msg}"
        if KazumiRequestHandler.logger_callback:
            KazumiRequestHandler.logger_callback(log_str)

    def do_GET(self):
        try:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            query = urllib.parse.parse_qs(parsed.query)

            if path == '/api/search':
                keyword = query.get('q', [''])[0].strip().lower()
                results = []
                for item in self.library_data:
                    if not keyword or keyword in item['title'].lower() or keyword in item['raw_title'].lower():
                        results.append({
                            'id': item['id'],
                            'name': item['title']
                        })
                self.send_json({'code': 200, 'data': results})
                self.log_custom(200, f"搜索: '{keyword}' ({len(results)} 条命中)")

            elif path.startswith('/api/detail/'):
                source_id = path.split('/')[-1]
                target = next((item for item in self.library_data if item['id'] == source_id), None)
                if target:
                    episodes_list = []
                    for ep in target['episodes']:
                        encoded_path = urllib.parse.quote(ep['abs_path'])
                        episodes_list.append({
                            'name': f"第 {ep['ep_num']} 集",
                            'url': f"/play?file={encoded_path}"
                        })
                    res_data = {
                        'code': 200,
                        'data': {
                            'id': target['id'],
                            'playSources': [
                                {
                                    'name': '本地原画',
                                    'episodes': episodes_list
                                }
                            ]
                        }
                    }
                    self.send_json(res_data)
                    self.log_custom(200, f"加载剧集: 「{target['title']}」 ({len(episodes_list)} 集)")
                else:
                    self.send_json({'code': 404, 'msg': '未找到对应番剧'}, status=404)
                    self.log_custom(404, f"未找到 ID: {source_id}")

            elif path == '/play':
                file_abs = query.get('file', [''])[0]
                html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>localPartner Stream</title>
    <style>
        body, html {{ margin: 0; padding: 0; width: 100%; height: 100%; background: #000; overflow: hidden; }}
        video {{ width: 100%; height: 100%; object-fit: contain; }}
    </style>
</head>
<body>
    <video controls autoplay playsinline src="/stream?file={file_abs}"></video>
</body>
</html>"""
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(html_content.encode('utf-8'))
                self.log_custom(200, "加载播放页")

            elif path == '/stream':
                file_abs = urllib.parse.unquote(query.get('file', [''])[0])
                file_path = os.path.abspath(file_abs)

                is_allowed = any(file_path.startswith(os.path.abspath(d)) for d in self.allowed_dirs)
                if not is_allowed or not os.path.isfile(file_path):
                    self.send_error(403, "Access Denied / File Not Found")
                    self.log_custom(403, "拒绝访问或文件不存在")
                    return

                self.serve_video_range(file_path)

            else:
                self.send_error(404, "Not Found")
                self.log_custom(404, "未知路径")

        except Exception as e:
            if KazumiRequestHandler.logger_callback:
                KazumiRequestHandler.logger_callback(f"[错误] 系统异常: {e}")

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def serve_video_range(self, file_path):
        file_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        mime_type, _ = mimetypes.guess_type(file_path)
        if not mime_type:
            mime_type = 'video/x-matroska' if file_path.endswith('.mkv') else 'video/mp4'

        range_header = self.headers.get('Range')
        if range_header:
            match = re.search(r'bytes=(\d+)-(\d+)?', range_header)
            if match:
                start = int(match.group(1))
                end = int(match.group(2)) if match.group(2) else file_size - 1
                if start >= file_size:
                    self.send_error(416, "Requested Range Not Satisfiable")
                    return
                end = min(end, file_size - 1)
                length = end - start + 1

                self.send_response(206)
                self.send_header('Content-Type', mime_type)
                self.send_header('Accept-Ranges', 'bytes')
                self.send_header('Content-Range', f'bytes {start}-{end}/{file_size}')
                self.send_header('Content-Length', str(length))
                self.end_headers()

                self.log_custom(206, f"分段推流 [{start}-{end}/{file_size}] {file_name}")

                with open(file_path, 'rb') as f:
                    f.seek(start)
                    remaining = length
                    while remaining > 0:
                        chunk_size = min(65536, remaining)
                        data = f.read(chunk_size)
                        if not data:
                            break
                        self.wfile.write(data)
                        remaining -= len(data)
                return

        self.send_response(200)
        self.send_header('Content-Type', mime_type)
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Content-Length', str(file_size))
        self.end_headers()

        self.log_custom(200, f"全量推流 {file_name}")

        with open(file_path, 'rb') as f:
            while True:
                data = f.read(65536)
                if not data:
                    break
                self.wfile.write(data)


# ==================== GUI Kazumi API 配置指南面板 (需求 1 改进) ====================
class ApiConfigTab(scrolled.ScrolledPanel):
    """精准控制复制按钮与预留右侧滚动条缓冲区的 Kazumi API 指南面板"""
    def __init__(self, parent):
        super().__init__(parent)
        self.SetBackgroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_FRAMEBK))
        self.SetupScrolling(scroll_x=False, scroll_y=True)

        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.fields = {}

        # 顶部简单说明文案 (移除全量复制按钮)
        top_tip = wx.StaticText(self, label="说明：以下为 Kazumi 自定义规则所需字段及配置值。")
        top_tip.SetForegroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_GRAYTEXT))
        self.sizer.Add(top_tip, 0, wx.ALL, 4)

        # 1. 基础配置
        self._create_group("【基础配置】", [
            ("规则名称", "localPartner"),
            ("规则版本", APP_VERSION),
            ("基础地址", "http://127.0.0.1:8080/"),
            ("搜索规则类型", "API"),
            ("选集规则类型", "API")
        ])

        # 2. 搜索规则配置
        self._create_group("【搜索规则配置 (searchApiConfig)】", [
            ("搜索请求方法", "GET"),
            ("搜索请求地址", "http://127.0.0.1:8080/api/search"),
            ("搜索请求头", "留空"),
            ("搜索查询参数", '{"q":"@keyword"}'),
            ("搜索请求体类型", "无"),
            ("搜索结果列表路径", "$.data[*]"),
            ("条目名称路径", "$.name"),
            ("条目来源路径", "$.id")
        ])

        # 3. 选集规则配置
        self._create_group("【选集规则配置 (chapterApiConfig)】", [
            ("选集请求方法", "GET"),
            ("选集请求地址", "http://127.0.0.1:8080/api/detail/@source"),
            ("选集请求头", "留空"),
            ("选集查询参数", "留空"),
            ("选集请求体类型", "无"),
            ("选集响应格式", "嵌套JSON"),
            ("播放线路列表路径", "$.data.playSources[*]"),
            ("线路名称路径", "$.name"),
            ("剧集列表路径", "$.episodes[*]"),
            ("剧集名称路径", "$.name"),
            ("播放入口地址路径", "$.url"),
            ("响应变量", "留空"),
            ("播放页地址模板", "留空"),
            ("播放页查询参数", "留空")
        ])

        self.SetSizer(self.sizer)
        self.FitInside()

    def _should_show_copy_button(self, label_text, default_val):
        """规则判断：值是“留空”或名称含“类型”“格式”“方法”的不提供复制按钮"""
        if default_val == "留空":
            return False
        for kw in ["类型", "格式", "方法"]:
            if kw in label_text:
                return False
        return True

    def _create_group(self, title, items):
        sb = wx.StaticBox(self, label=title)
        sb_sizer = wx.StaticBoxSizer(sb, wx.VERTICAL)
        grid = wx.FlexGridSizer(cols=3, vgap=3, hgap=6)
        grid.AddGrowableCol(1, 1)

        for label_text, default_val in items:
            # 宽标签列 (125px)，防止挤压
            lbl = wx.StaticText(self, label=label_text + ":", size=(125, -1), style=wx.ALIGN_RIGHT)
            lbl.SetFont(wx.Font(8, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))

            tc = wx.TextCtrl(self, value=default_val, size=(-1, 21), style=wx.TE_READONLY)
            tc.SetBackgroundColour(wx.Colour(250, 250, 250))

            grid.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL)
            grid.Add(tc, 1, wx.EXPAND | wx.ALIGN_CENTER_VERTICAL)

            # 按规则筛选是否生成“复制”按钮，否则用空白控件占位保持网格对齐
            if self._should_show_copy_button(label_text, default_val):
                btn_copy = wx.Button(self, label="复制", size=(38, 20))
                btn_copy.Bind(wx.EVT_BUTTON, lambda evt, val_ctrl=tc: self._copy_to_clip(val_ctrl.GetValue()))
                grid.Add(btn_copy, 0, wx.ALIGN_CENTER_VERTICAL)
            else:
                grid.Add((38, 20), 0)

            self.fields[label_text] = tc

        # 重点：右侧预留 16px 边距，避免纵向滚动条遮挡控件或触发横向滚动条
        sb_sizer.Add(grid, 1, wx.EXPAND | wx.ALL, 3)
        self.sizer.Add(sb_sizer, 0, wx.EXPAND | wx.LEFT | wx.TOP | wx.RIGHT, 4)

    def update_dynamic_urls(self, base_url, app_version):
        """服务启动后更新实际生成的动态 URL"""
        if "基础地址" in self.fields:
            self.fields["基础地址"].SetValue(f"{base_url}/")
        if "规则版本" in self.fields:
            self.fields["规则版本"].SetValue(str(app_version))
        if "搜索请求地址" in self.fields:
            self.fields["搜索请求地址"].SetValue(f"{base_url}/api/search")
        if "选集请求地址" in self.fields:
            self.fields["选集请求地址"].SetValue(f"{base_url}/api/detail/@source")

    def _copy_to_clip(self, text):
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(text))
            wx.TheClipboard.Close()
            wx.MessageBox("已复制到剪贴板！", "提示", wx.OK | wx.ICON_INFORMATION)


# ==================== GUI 彩色日志显示面板 ====================
class ColoredLogPanel(wx.Panel):
    def __init__(self, parent):
        super().__init__(parent)
        self.SetBackgroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_FRAMEBK))
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.rtc = rt.RichTextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL)
        self.rtc.SetFont(wx.Font(9, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        sizer.Add(self.rtc, 1, wx.EXPAND | wx.ALL, 1)
        self.SetSizer(sizer)

    def append_log(self, text):
        wx.CallAfter(self._write_color_log, text)

    def _write_color_log(self, text):
        if not self or not self.rtc:
            return
        self.rtc.MoveEnd()

        if "[200]" in text or "成功" in text:
            self.rtc.BeginTextColour(wx.Colour(46, 125, 50))
        elif "[206]" in text:
            self.rtc.BeginTextColour(wx.Colour(0, 131, 143))
        elif "[403]" in text or "[404]" in text or "警告" in text or "超时" in text:
            self.rtc.BeginTextColour(wx.Colour(230, 81, 0))
        elif "错误" in text or "ERROR" in text or "失败" in text:
            self.rtc.BeginTextColour(wx.Colour(198, 40, 40))
        elif "===" in text:
            self.rtc.BeginTextColour(wx.Colour(21, 101, 192))
        else:
            self.rtc.BeginTextColour(wx.Colour(50, 50, 50))

        self.rtc.WriteText(text + "\n")
        self.rtc.EndTextColour()
        self.rtc.ShowPosition(self.rtc.GetLastPosition())


# ==================== GUI 番剧条目卡片 ====================
class AnimeItemPanel(wx.Panel):
    def __init__(self, parent, anime_info):
        super().__init__(parent, style=wx.BORDER_THEME)
        self.anime_info = anime_info
        self.SetBackgroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOW))

        main_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.bmp_ctrl = wx.StaticBitmap(self, size=(70, 100))
        self.bmp_ctrl.SetBitmap(create_placeholder_bitmap(text="加载中..."))
        main_sizer.Add(self.bmp_ctrl, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 4)

        info_sizer = wx.BoxSizer(wx.VERTICAL)

        title_sizer = wx.BoxSizer(wx.HORIZONTAL)
        title_font = wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT)
        title_font.SetWeight(wx.FONTWEIGHT_BOLD)

        title_lbl = wx.StaticText(self, label=anime_info['title'])
        title_lbl.SetFont(title_font)
        title_sizer.Add(title_lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)

        if anime_info['match_success']:
            status_tag = wx.StaticText(self, label=f"[{anime_info['source_tag']}]")
            status_tag.SetForegroundColour(wx.Colour(46, 125, 50))
        else:
            status_tag = wx.StaticText(self, label="[纯本地名称]")
            status_tag.SetForegroundColour(wx.Colour(180, 100, 0))
        title_sizer.Add(status_tag, 0, wx.ALIGN_CENTER_VERTICAL)

        info_sizer.Add(title_sizer, 0, wx.BOTTOM, 2)

        raw_title_lbl = wx.StaticText(self, label=f"原始名称: {anime_info['raw_title']}")
        raw_title_lbl.SetForegroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_GRAYTEXT))
        info_sizer.Add(raw_title_lbl, 0, wx.BOTTOM, 2)

        ep_count = len(anime_info['episodes'])
        if ep_count > 0:
            first_ep = anime_info['episodes'][0]['ep_num']
            last_ep = anime_info['episodes'][-1]['ep_num']
            ep_range = f"[{first_ep}] ~ [{last_ep}]" if ep_count > 1 else f"[{first_ep}]"
        else:
            ep_range = "无"
        fmt_str = ", ".join(anime_info['formats']) if anime_info['formats'] else "未知"

        ep_lbl = wx.StaticText(self, label=f"集数: {ep_count} 集 ({ep_range})  |  格式: {fmt_str}")
        info_sizer.Add(ep_lbl, 0, wx.BOTTOM, 2)

        meta = anime_info['metadata']
        meta_items = []
        if meta['release_groups']:
            meta_items.append(f"字幕组: {', '.join(meta['release_groups'])}")
        if meta['resolutions']:
            meta_items.append(f"清晰度: {', '.join(meta['resolutions'])}")
        if meta['video_codecs']:
            meta_items.append(f"编码: {', '.join(meta['video_codecs'])}")

        meta_str = "  |  ".join(meta_items) if meta_items else "无额外元数据"
        meta_lbl = wx.StaticText(self, label=meta_str)
        meta_lbl.SetForegroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_GRAYTEXT))
        info_sizer.Add(meta_lbl, 0, wx.BOTTOM, 2)

        main_sizer.Add(info_sizer, 1, wx.ALL | wx.EXPAND, 4)
        self.SetSizer(main_sizer)

        if anime_info.get('cover_url'):
            threading.Thread(target=self._load_cover_async, args=(anime_info['cover_url'],), daemon=True).start()
        else:
            self.bmp_ctrl.SetBitmap(create_placeholder_bitmap(text="无海报"))

    def _load_cover_async(self, cover_url):
        bmp = download_image_as_bitmap(cover_url)
        if bmp:
            wx.CallAfter(self._update_bitmap, bmp)
        else:
            wx.CallAfter(self._update_bitmap, create_placeholder_bitmap(text="无海报"))

    def _update_bitmap(self, bmp):
        if self and self.bmp_ctrl:
            self.bmp_ctrl.SetBitmap(bmp)
            self.Refresh()


# ==================== GUI 关于对话框 ====================
class CustomAboutDialog(wx.Dialog):
    def __init__(self, parent):
        super().__init__(parent, title="About", size=(340, 210))
        self.SetBackgroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_FRAMEBK))

        sizer = wx.BoxSizer(wx.VERTICAL)
        h_sizer = wx.BoxSizer(wx.HORIZONTAL)

        icon_path = resource_path("sakura.ico")
        if not os.path.exists(icon_path):
            icon_path = resource_path("sakura.png")

        if os.path.exists(icon_path):
            try:
                img = wx.Image(icon_path).Scale(56, 56, wx.IMAGE_QUALITY_HIGH)
                bmp_ctrl = wx.StaticBitmap(self, bitmap=wx.Bitmap(img))
            except Exception:
                bmp_ctrl = wx.StaticBitmap(self, bitmap=wx.ArtProvider.GetBitmap(wx.ART_INFORMATION, size=(48, 48)))
        else:
            bmp_ctrl = wx.StaticBitmap(self, bitmap=wx.ArtProvider.GetBitmap(wx.ART_INFORMATION, size=(48, 48)))

        h_sizer.Add(bmp_ctrl, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 10)

        info_sizer = wx.BoxSizer(wx.VERTICAL)

        title_font = wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT)
        title_font.SetWeight(wx.FONTWEIGHT_BOLD)
        title_font.SetPointSize(11)

        name_lbl = wx.StaticText(self, label="localPartner")
        name_lbl.SetFont(title_font)
        info_sizer.Add(name_lbl, 0, wx.BOTTOM, 4)

        ver_lbl = wx.StaticText(self, label=f"v{APP_VERSION}")
        dev_lbl = wx.StaticText(self, label=f"by {DEVELOPER_NAME}")
        github_url = "https://github.com/bh983/localPartner"
        link_ctrl = wx.adv.HyperlinkCtrl(
            self,
            id=wx.ID_ANY,
            label="GitHub 项目主页",
            url=github_url
        )
        info_sizer.Add(ver_lbl, 0, wx.BOTTOM, 2)
        info_sizer.Add(dev_lbl, 0, wx.BOTTOM, 2)
        info_sizer.Add(link_ctrl, 0)

        h_sizer.Add(info_sizer, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        sizer.Add(h_sizer, 1, wx.EXPAND | wx.ALL, 5)

        btn_close = wx.Button(self, wx.ID_OK, label="确定", size=(80, 24))
        sizer.Add(btn_close, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.BOTTOM, 8)

        self.SetSizer(sizer)
        self.CenterOnParent()
        
# ==================== 主窗口 GUI 界面 (需求 2 布局重构) ====================
class MainFrame(wx.Frame):
    def __init__(self):
        super().__init__(None, title=f"{APP_NAME} v{APP_VERSION}", size=(960, 680))
        self.SetMinSize((850, 580))
        self.SetBackgroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_FRAMEBK))
        self.Center()

        icon_path = resource_path("sakura.ico")
        if os.path.exists(icon_path):
            try:
                self.SetIcon(wx.Icon(icon_path))
            except Exception:
                pass

        self.search_dirs = []
        self.library_data = []
        self.server_instance = None

        self._init_ui()
        self._init_statusbar()

        self.Bind(wx.EVT_CLOSE, self.on_close)

    def _init_ui(self):
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # 1. 顶部配置区域
        top_panel = wx.Panel(self)
        top_panel.SetBackgroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_FRAMEBK))
        top_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # 1.1 媒体检索配置区 (原“扫描目录设置”)
        dir_box = wx.StaticBox(top_panel, label="媒体检索配置")
        dir_sizer = wx.StaticBoxSizer(dir_box, wx.VERTICAL)

        self.dir_listbox = wx.ListBox(top_panel, style=wx.LB_SINGLE, size=(-1, 62))
        dir_sizer.Add(self.dir_listbox, 1, wx.EXPAND | wx.ALL, 2)

        dir_btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_add_dir = wx.Button(top_panel, label="添加目录...", size=(75, 23))
        self.btn_del_dir = wx.Button(top_panel, label="移除选中", size=(75, 23))
        dir_btn_sizer.Add(self.btn_add_dir, 0, wx.RIGHT, 4)
        dir_btn_sizer.Add(self.btn_del_dir, 0)
        dir_sizer.Add(dir_btn_sizer, 0, wx.ALIGN_RIGHT | wx.TOP, 2)

        top_sizer.Add(dir_sizer, 1, wx.EXPAND | wx.RIGHT, 4)

        # 1.2 服务控制区 (原“服务控制与检索 API 设置”)
        ctrl_box = wx.StaticBox(top_panel, label="服务控制")
        ctrl_sizer = wx.StaticBoxSizer(ctrl_box, wx.VERTICAL)

        # 第一行：联网检索源 + 端口 + 悬停提示图标
        top_row_sizer = wx.BoxSizer(wx.HORIZONTAL)
        api_label = wx.StaticText(top_panel, label="联网检索源:")
        self.choice_api = wx.Choice(top_panel, choices=["萌娘百科 (默认)", "Bangumi", "无 (不开启)"])
        self.choice_api.SetSelection(0)

        port_label = wx.StaticText(top_panel, label="端口:")
        self.port_ctrl = wx.TextCtrl(top_panel, value=str(DEFAULT_PORT), size=(45, -1))

        # 帮助图标 (仅鼠标悬停时显示 Tooltip)
        help_bmp = wx.ArtProvider.GetBitmap(wx.ART_HELP, wx.ART_BUTTON, (16, 16))
        self.help_icon = wx.StaticBitmap(top_panel, bitmap=help_bmp)
        help_tip_text = ("联网检索后，localPartner反馈给kazumi的番剧名将采用获取到的名称。"
                         "若未采用Bangumi搜索源（需要特殊网络环境），番剧名可能与kazumi中不一致，需要在kazumi里手动输入localPartner中的番剧名检索")
        self.help_icon.SetToolTip(help_tip_text)

        top_row_sizer.Add(api_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 3)
        top_row_sizer.Add(self.choice_api, 1, wx.ALIGN_CENTER_VERTICAL)
        top_row_sizer.Add(port_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 6)
        top_row_sizer.Add(self.port_ctrl, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 3)
        top_row_sizer.Add(self.help_icon, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 6)
        ctrl_sizer.Add(top_row_sizer, 0, wx.EXPAND | wx.BOTTOM, 4)

        # 第二行：核心步骤按钮 [1. 开始扫描] [2. 启动服务] [停止服务]
        btn_action_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_scan = wx.Button(top_panel, label="1. 开始扫描", size=(90, 24))
        self.btn_start_server = wx.Button(top_panel, label="2. 启动服务", size=(90, 24))
        self.btn_stop_server = wx.Button(top_panel, label="停止服务", size=(75, 24))

        self.btn_start_server.Enable(False)
        self.btn_stop_server.Enable(False)

        btn_action_sizer.Add(self.btn_scan, 1, wx.RIGHT, 3)
        btn_action_sizer.Add(self.btn_start_server, 1, wx.RIGHT, 3)
        btn_action_sizer.Add(self.btn_stop_server, 0)
        ctrl_sizer.Add(btn_action_sizer, 0, wx.EXPAND | wx.BOTTOM, 4)

        # 第三行：关于按钮（挪至开始扫描那一行的下方，铺满底部防止留空）
        btn_about_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_about = wx.Button(top_panel, label="关于 localPartner", size=(-1, 23))
        btn_about_sizer.Add(self.btn_about, 1, wx.EXPAND)
        ctrl_sizer.Add(btn_about_sizer, 0, wx.EXPAND)

        top_sizer.Add(ctrl_sizer, 1, wx.EXPAND)

        top_panel.SetSizer(top_sizer)
        main_sizer.Add(top_panel, 0, wx.EXPAND | wx.ALL, 4)

        # 2. 中央 Splitter 拆分区域
        splitter = wx.SplitterWindow(self, style=wx.SP_3D | wx.SP_LIVE_UPDATE)

        left_panel = wx.Panel(splitter)
        left_panel.SetBackgroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_FRAMEBK))
        left_sizer = wx.BoxSizer(wx.VERTICAL)
        res_label = wx.StaticText(left_panel, label="媒体库检索结果:")
        res_label.SetFont(wx.Font(9, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        left_sizer.Add(res_label, 0, wx.ALL, 2)

        self.result_scrolled = scrolled.ScrolledPanel(left_panel, style=wx.SUNKEN_BORDER)
        self.result_scrolled.SetBackgroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_FRAMEBK))
        self.result_scrolled.SetupScrolling()
        self.result_sizer = wx.BoxSizer(wx.VERTICAL)
        self.result_scrolled.SetSizer(self.result_sizer)

        left_sizer.Add(self.result_scrolled, 1, wx.EXPAND | wx.ALL, 1)
        left_panel.SetSizer(left_sizer)

        right_panel = wx.Panel(splitter)
        right_panel.SetBackgroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_FRAMEBK))
        right_sizer = wx.BoxSizer(wx.VERTICAL)

        notebook = wx.Notebook(right_panel)

        self.log_tab = ColoredLogPanel(notebook)
        notebook.AddPage(self.log_tab, "运行日志")

        self.api_tab = ApiConfigTab(notebook)
        notebook.AddPage(self.api_tab, "Kazumi API 指南")

        right_sizer.Add(notebook, 1, wx.EXPAND | wx.ALL, 1)
        right_panel.SetSizer(right_sizer)

        splitter.SplitVertically(left_panel, right_panel, 520)
        splitter.SetMinimumPaneSize(200)

        main_sizer.Add(splitter, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 4)
        self.SetSizer(main_sizer)

        # 事件绑定
        self.btn_add_dir.Bind(wx.EVT_BUTTON, self.on_add_dir)
        self.btn_del_dir.Bind(wx.EVT_BUTTON, self.on_del_dir)
        self.btn_about.Bind(wx.EVT_BUTTON, self.on_about)
        self.btn_scan.Bind(wx.EVT_BUTTON, self.on_scan_click)
        self.btn_start_server.Bind(wx.EVT_BUTTON, self.on_start_server_click)
        self.btn_stop_server.Bind(wx.EVT_BUTTON, self.on_stop_server_click)

        KazumiRequestHandler.logger_callback = self.log_tab.append_log

    def _init_statusbar(self):
        self.statusbar = self.CreateStatusBar(3)
        self.statusbar.SetBackgroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_FRAMEBK))
        self.statusbar.SetStatusWidths([-2, -2, -1])
        self._update_status_bar("● 服务未启动", get_local_ip(), 0)

    def _update_status_bar(self, status_text, ip_text, count):
        self.statusbar.SetStatusText(status_text, 0)
        self.statusbar.SetStatusText(f"IP: {ip_text}", 1)
        self.statusbar.SetStatusText(f"已载入: {count} 部", 2)

    def on_about(self, event):
        dlg = CustomAboutDialog(self)
        dlg.ShowModal()
        dlg.Destroy()

    def on_add_dir(self, event):
        dlg = wx.DirDialog(self, "选择要扫描的动画媒体文件夹", style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST)
        if dlg.ShowModal() == wx.ID_OK:
            path = dlg.GetPath()
            if path not in self.search_dirs:
                self.search_dirs.append(path)
                self.dir_listbox.Append(path)
        dlg.Destroy()

    def on_del_dir(self, event):
        sel = self.dir_listbox.GetSelection()
        if sel != wx.NOT_FOUND:
            self.search_dirs.pop(sel)
            self.dir_listbox.Delete(sel)

    # --- 逻辑控制：扫描媒体文件 ---
    def on_scan_click(self, event):
        if not self.search_dirs:
            wx.MessageBox("请至少添加一个扫描目录！", "提示", wx.OK | wx.ICON_WARNING)
            return

        self.btn_scan.Enable(False)
        self.btn_start_server.Enable(False)
        self.btn_add_dir.Enable(False)
        self.btn_del_dir.Enable(False)

        self._update_status_bar("◐ 正在扫描媒体文件...", get_local_ip(), len(self.library_data))
        threading.Thread(target=self._scan_worker, daemon=True).start()

    def _scan_worker(self):
        self.log_tab.append_log("=== 开始执行本地媒体库扫描 ===")
        raw_anime_map = {}

        for target_dir in self.search_dirs:
            if not os.path.exists(target_dir):
                continue

            for root, dirs, files in os.walk(target_dir):
                rel_path = os.path.relpath(root, target_dir)
                depth = 0 if rel_path == '.' else len(rel_path.replace('\\', '/').split('/'))
                if depth >= 1:
                    dirs.clear()

                folder_name = os.path.basename(root)
                for file in files:
                    ext = os.path.splitext(file)[1].lower()
                    if ext not in SUPPORTED_EXTS:
                        continue

                    abs_file_path = os.path.abspath(os.path.join(root, file))
                    parsed = anitopy.parse(file)

                    anime_title = parsed.get("anime_title")
                    title_source = "parsed"
                    if not anime_title or not anime_title.strip():
                        anime_title = folder_name
                        title_source = "folder_fallback"

                    ep_num = parsed.get("episode_number")
                    if isinstance(ep_num, list):
                        ep_num = str(ep_num[0]) if ep_num else None
                    if not ep_num:
                        ep_num = fallback_extract_episode(file)
                    else:
                        ep_num = str(ep_num)

                    if anime_title not in raw_anime_map:
                        raw_anime_map[anime_title] = {
                            'raw_title': anime_title,
                            'title_source': title_source,
                            'fallback_folder': folder_name if title_source == "folder_fallback" else "",
                            'episodes': [],
                            'formats': set(),
                            'metadata': {
                                'release_groups': set(),
                                'resolutions': set(),
                                'video_codecs': set(),
                                'audio_codecs': set(),
                            }
                        }

                    group = raw_anime_map[anime_title]
                    group['formats'].add(ext.lstrip('.'))
                    if parsed.get("release_group"):
                        group['metadata']['release_groups'].add(parsed.get("release_group"))
                    if parsed.get("video_resolution"):
                        group['metadata']['resolutions'].add(parsed.get("video_resolution"))
                    if parsed.get("video_term"):
                        group['metadata']['video_codecs'].add(parsed.get("video_term"))
                    if parsed.get("audio_term"):
                        group['metadata']['audio_codecs'].add(parsed.get("audio_term"))

                    group['episodes'].append({
                        'ep_num': ep_num,
                        'file_name': file,
                        'abs_path': abs_file_path
                    })

        self.log_tab.append_log(f"本地文件检索完成，共汇总 {len(raw_anime_map)} 部动画标题。")

        api_selection = self.choice_api.GetStringSelection()
        library = []
        fallback_id = 1
        network_disabled_by_timeout = False

        for raw_title, group in raw_anime_map.items():
            if not group['episodes']:
                continue
            group['episodes'].sort(key=lambda x: ep_sort_key(x['ep_num']))

            final_title = raw_title
            item_id = str(fallback_id)
            cover_url = None
            match_success = False
            source_tag = "纯本地名称"

            if api_selection != "无 (不开启)" and not network_disabled_by_timeout:
                if "萌娘百科" in api_selection:
                    self.log_tab.append_log(f"萌娘百科 API 检索: 「{raw_title}」...")
                    cn_name, m_id, cover, is_timeout = fetch_moegirl_info_online(raw_title)
                    source_tag = "萌娘百科"
                else:
                    self.log_tab.append_log(f"Bangumi API 检索: 「{raw_title}」...")
                    cn_name, m_id, cover, is_timeout = fetch_bangumi_info_online(raw_title)
                    source_tag = "Bangumi"

                if is_timeout:
                    network_disabled_by_timeout = True
                    self.log_tab.append_log(f"[警告] 连接 {source_tag} API 超时！已自动取消后续所有联网检索，改用本地名称处理。")
                elif cn_name:
                    final_title = cn_name
                    item_id = m_id or str(fallback_id)
                    cover_url = cover
                    match_success = True
                    self.log_tab.append_log(f"  -> 匹配成功: 「{cn_name}」 (ID: {item_id})")
                else:
                    self.log_tab.append_log(f"  -> 未找到 API 匹配结果。")

            fallback_id += 1

            library.append({
                'id': item_id,
                'title': final_title,
                'raw_title': raw_title,
                'match_success': match_success,
                'source_tag': source_tag,
                'cover_url': cover_url,
                'formats': sorted(list(group['formats'])),
                'episodes': group['episodes'],
                'metadata': group['metadata']
            })

        self.library_data = library
        wx.CallAfter(self._on_scan_finished, library)

    def _on_scan_finished(self, library):
        self._update_result_scrolled_ui(library)
        self.btn_scan.Enable(True)
        self.btn_add_dir.Enable(True)
        self.btn_del_dir.Enable(True)

        if library:
            self.btn_start_server.Enable(True)
            self.log_tab.append_log(f"=== 媒体库扫描完成，可点击 [2. 启动服务] ===")
            self._update_status_bar("● 扫描完成 (可启动服务)", get_local_ip(), len(library))
        else:
            self.log_tab.append_log("[提示] 未发现在支持范围内的视频文件。")
            self._update_status_bar("● 扫描完成 (未找到文件)", get_local_ip(), 0)

    # --- 启动/停止 HTTP 服务 ---
    def on_start_server_click(self, event):
        if not self.library_data:
            wx.MessageBox("请先执行扫描并确保检索到媒体文件！", "提示", wx.OK | wx.ICON_WARNING)
            return

        try:
            port = int(self.port_ctrl.GetValue().strip())
        except ValueError:
            wx.MessageBox("请输入有效的端口号！", "提示", wx.OK | wx.ICON_ERROR)
            return

        self.btn_scan.Enable(False)
        self.btn_start_server.Enable(False)
        threading.Thread(target=self._start_server_worker, args=(port,), daemon=True).start()

    def _start_server_worker(self, port):
        self.log_tab.append_log("正在绑定端口并启动多线程 HTTP 服务端...")
        KazumiRequestHandler.library_data = self.library_data
        KazumiRequestHandler.allowed_dirs = self.search_dirs

        actual_port = port
        server = None
        for attempt in range(5):
            try:
        # 使用修缮后的 ThreadedHTTPServer6，绑定 '' (即 ::)
                server = ThreadedHTTPServer6(('', actual_port), KazumiRequestHandler)
                break
            except OSError as e:
                if e.errno in (98, 10048):
                    self.log_tab.append_log(f"[提示] 端口 {actual_port} 被占用，自动切换至 {actual_port + 1}...")
                    actual_port += 1
                else:
                    break

        if not server:
            self.log_tab.append_log("[错误] 服务启动失败：端口绑定失败！")
            wx.CallAfter(self._on_server_start_failed)
            return

        self.server_instance = server
        local_ip = get_local_ip()
        base_url = f"http://{local_ip}:{actual_port}"

        wx.CallAfter(self._on_server_start_success, actual_port, local_ip, base_url)
        server.serve_forever()

    def _on_server_start_success(self, port, ip, base_url):
        self.btn_stop_server.Enable(True)
        self.port_ctrl.SetValue(str(port))
        self._update_status_bar(f"● 服务运行中 ({base_url}/)", f"{ip}:{port}", len(self.library_data))
        self.api_tab.update_dynamic_urls(base_url, APP_VERSION)
        self.log_tab.append_log(f"=== 服务成功启动！监听地址: {base_url}/ ===")

    def _on_server_start_failed(self):
        self.btn_scan.Enable(True)
        self.btn_start_server.Enable(True)
        self._update_status_bar("● 服务启动失败", get_local_ip(), len(self.library_data))

    def on_stop_server_click(self, event):
        if self.server_instance:
            self.log_tab.append_log("正在停止 HTTP 服务...")
            threading.Thread(target=self.server_instance.shutdown, daemon=True).start()
            self.server_instance = None

        self.btn_scan.Enable(True)
        self.btn_start_server.Enable(True)
        self.btn_stop_server.Enable(False)

        self._update_status_bar("● 服务已停止", get_local_ip(), len(self.library_data))
        self.log_tab.append_log("=== HTTP 服务已安全关闭 ===")

    def _update_result_scrolled_ui(self, library):
        self.result_sizer.Clear(True)
        if not library:
            no_data_lbl = wx.StaticText(self.result_scrolled, label="未找到支持的动画视频文件。")
            self.result_sizer.Add(no_data_lbl, 0, wx.ALL, 10)
        else:
            for item in library:
                item_panel = AnimeItemPanel(self.result_scrolled, item)
                self.result_sizer.Add(item_panel, 0, wx.EXPAND | wx.ALL, 3)

        self.result_scrolled.Layout()
        self.result_scrolled.SetupScrolling()

    def on_close(self, event):
        if self.server_instance:
            try:
                threading.Thread(target=self.server_instance.shutdown, daemon=True).start()
            except Exception:
                pass
        self.Destroy()


# ==================== 程序主入口 ====================
def main():
    app = wx.App(False)
    frame = MainFrame()
    frame.Show()
    app.MainLoop()


if __name__ == '__main__':
    main()
