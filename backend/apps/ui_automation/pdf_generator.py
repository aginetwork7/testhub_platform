"""
AI测试报告PDF生成器
使用reportlab生成专业的PDF报告
"""
import os
from html import escape
from datetime import datetime
from typing import Dict, Any
from io import BytesIO

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    REPORTLAB_AVAILABLE = True
except ImportError as e:
    REPORTLAB_AVAILABLE = False
    import logging
    logger = logging.getLogger('django')
    logger.warning(f"reportlab import failed: {e}")

import logging
logger = logging.getLogger('django')


class AIReportPDFGenerator:
    """AI测试报告PDF生成器"""

    def __init__(self, report_data: Dict[str, Any], report_type: str = 'summary', report_category: str = 'ui_automation'):
        """
        初始化PDF生成器

        Args:
            report_data: 报告数据
            report_type: 报告类型 (summary/detailed/performance)
        """
        if not REPORTLAB_AVAILABLE:
            raise ImportError("reportlab 库未安装，请运行: pip install reportlab")

        self.report_data = report_data
        self.report_type = report_type
        self.report_category = report_category
        self.buffer = BytesIO()

        # 注册中文字体
        self._register_fonts()

        # 创建样式
        self.theme = self._get_theme()
        self.styles = self._create_styles()

    def _get_theme(self):
        if self.report_category == 'ai_testing':
            return {
                'title_prefix': 'AI智能测试',
                'title_color': colors.HexColor('#0f4c81'),
                'heading_color': colors.HexColor('#125d98'),
                'subheading_color': colors.HexColor('#3c6e71'),
                'text_color': colors.HexColor('#243b53'),
                'muted_color': colors.HexColor('#5c677d'),
                'accent': colors.HexColor('#1f8ef1'),
                'accent_soft': colors.HexColor('#eaf4ff'),
                'success': colors.HexColor('#19a974'),
                'danger': colors.HexColor('#d64545'),
                'border': colors.HexColor('#b8c4d6'),
                'footer_text': 'TestHub AI Testing Report',
            }
        return {
            'title_prefix': 'AI测试执行',
            'title_color': colors.HexColor('#2c3e50'),
            'heading_color': colors.HexColor('#34495e'),
            'subheading_color': colors.HexColor('#7f8c8d'),
            'text_color': colors.HexColor('#2c3e50'),
            'muted_color': colors.HexColor('#7f8c8d'),
            'accent': colors.HexColor('#3498db'),
            'accent_soft': colors.HexColor('#ecf0f1'),
            'success': colors.HexColor('#27ae60'),
            'danger': colors.HexColor('#e74c3c'),
            'border': colors.grey,
            'footer_text': 'TestHub UI Automation Report',
        }

    def _register_fonts(self):
        """注册中文字体"""
        try:
            font_paths = [
                '/System/Library/Fonts/Supplemental/Arial Unicode.ttf',
                '/System/Library/Fonts/Supplemental/Songti.ttc',
                '/System/Library/Fonts/Supplemental/STHeiti Light.ttc',
                # Linux
                '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
                '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttf',
                '/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf',
                # Windows
                'C:/Windows/Fonts/simhei.ttf',
                'C:/Windows/Fonts/msyh.ttf',
            ]

            font_registered = False
            for font_path in font_paths:
                if os.path.exists(font_path):
                    try:
                        pdfmetrics.registerFont(TTFont('ChineseFont', font_path))
                        font_registered = True
                        logger.info(f"✅ Registered Chinese font: {font_path}")
                        break
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to register font {font_path}: {e}")
                        continue

            if not font_registered:
                try:
                    pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
                    self.font_name = 'STSong-Light'
                    font_registered = True
                    logger.info("✅ Registered fallback CID font: STSong-Light")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to register CID font STSong-Light: {e}")
                    self.font_name = 'Helvetica'
            else:
                self.font_name = 'ChineseFont'

        except Exception as e:
            logger.error(f"❌ Error registering fonts: {e}")
            self.font_name = 'Helvetica'

    def _create_styles(self):
        """创建文档样式"""
        styles = getSampleStyleSheet()

        # 自定义样式
        styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=styles['Heading1'],
            fontName=self.font_name,
            fontSize=24,
            textColor=self.theme['title_color'],
            spaceAfter=18,
            alignment=TA_CENTER,
            leading=30,
        ))

        styles.add(ParagraphStyle(
            name='CustomHeading2',
            parent=styles['Heading2'],
            fontName=self.font_name,
            fontSize=18,
            textColor=self.theme['heading_color'],
            spaceAfter=12,
            spaceBefore=20,
            leading=24,
        ))

        styles.add(ParagraphStyle(
            name='CustomHeading3',
            parent=styles['Heading3'],
            fontName=self.font_name,
            fontSize=14,
            textColor=self.theme['subheading_color'],
            spaceAfter=10,
            spaceBefore=15,
            leading=18,
        ))

        styles.add(ParagraphStyle(
            name='CustomNormal',
            parent=styles['Normal'],
            fontName=self.font_name,
            fontSize=11,
            textColor=self.theme['text_color'],
            spaceAfter=8,
            leading=16,
            wordWrap='CJK',
        ))

        styles.add(ParagraphStyle(
            name='CustomSmall',
            parent=styles['Normal'],
            fontName=self.font_name,
            fontSize=10,
            textColor=self.theme['muted_color'],
            leading=14,
            wordWrap='CJK',
        ))

        styles.add(ParagraphStyle(
            name='TableCell',
            parent=styles['CustomNormal'],
            fontSize=10,
            leading=14,
            spaceAfter=0,
            wordWrap='CJK',
        ))

        styles.add(ParagraphStyle(
            name='TableHeader',
            parent=styles['TableCell'],
            textColor=colors.whitesmoke,
        ))

        styles.add(ParagraphStyle(
            name='Footer',
            parent=styles['CustomSmall'],
            alignment=TA_CENTER,
            textColor=self.theme['muted_color'],
            fontSize=9,
            leading=12,
        ))

        return styles

    def _paragraph(self, value, style_name='TableCell'):
        text = '-' if value is None or value == '' else str(value)
        safe_text = escape(text).replace('\n', '<br/>')
        return Paragraph(safe_text, self.styles[style_name])

    def _build_table(self, rows, col_widths, header_rows=1, body_first_col_background=None, center_columns=None):
        formatted_rows = []
        for row_index, row in enumerate(rows):
            style_name = 'TableHeader' if row_index < header_rows else 'TableCell'
            formatted_rows.append([self._paragraph(cell, style_name) for cell in row])

        table = Table(formatted_rows, colWidths=col_widths, repeatRows=header_rows)
        style_commands = [
            ('FONTNAME', (0, 0), (-1, -1), self.font_name),
            ('GRID', (0, 0), (-1, -1), 0.5, self.theme['border']),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('BACKGROUND', (0, 0), (-1, header_rows - 1), self.theme['accent']),
            ('TEXTCOLOR', (0, 0), (-1, header_rows - 1), colors.whitesmoke),
        ]

        if body_first_col_background is not None and len(rows) > header_rows:
            style_commands.append(('BACKGROUND', (0, header_rows), (0, -1), body_first_col_background))

        for column_index in center_columns or []:
            style_commands.append(('ALIGN', (column_index, 0), (column_index, -1), 'CENTER'))

        table.setStyle(TableStyle(style_commands))
        return table

    def _draw_page_frame(self, canvas, doc):
        canvas.saveState()
        page_width, page_height = A4
        canvas.setStrokeColor(self.theme['accent'])
        canvas.setLineWidth(1.2)
        canvas.line(doc.leftMargin, page_height - 1.1 * cm, page_width - doc.rightMargin, page_height - 1.1 * cm)
        canvas.setStrokeColor(self.theme['border'])
        canvas.setLineWidth(0.6)
        canvas.line(doc.leftMargin, 1.2 * cm, page_width - doc.rightMargin, 1.2 * cm)
        canvas.setFont(self.font_name, 9)
        canvas.setFillColor(self.theme['muted_color'])
        canvas.drawString(doc.leftMargin, page_height - 0.8 * cm, self.theme['footer_text'])
        canvas.drawRightString(page_width - doc.rightMargin, page_height - 0.8 * cm, datetime.now().strftime('%Y-%m-%d %H:%M'))
        canvas.drawCentredString(page_width / 2, 0.7 * cm, f'第 {canvas.getPageNumber()} 页')
        canvas.restoreState()

    def generate(self) -> BytesIO:
        """
        生成PDF文档

        Returns:
            BytesIO: PDF文件的字节流
        """
        # 创建PDF文档
        doc = SimpleDocTemplate(
            self.buffer,
            pagesize=A4,
            rightMargin=2*cm,
            leftMargin=2*cm,
            topMargin=2*cm,
            bottomMargin=2*cm,
        )

        # 构建文档内容
        story = []
        story.extend(self._build_header())
        story.append(Spacer(1, 0.5*cm))

        # 根据报告类型生成不同内容
        if self.report_type == 'summary':
            story.extend(self._build_summary_report())
        elif self.report_type == 'detailed':
            story.extend(self._build_detailed_report())
        elif self.report_type == 'performance':
            story.extend(self._build_performance_report())

        # 生成PDF
        doc.build(story, onFirstPage=self._draw_page_frame, onLaterPages=self._draw_page_frame)
        self.buffer.seek(0)
        return self.buffer

    def _build_header(self):
        """构建报告头部"""
        story = []

        # 标题
        report_type_names = {
            'summary': '执行摘要报告',
            'detailed': '详细步骤报告',
            'performance': '性能分析报告'
        }
        title = f"{self.theme['title_prefix']} - {report_type_names.get(self.report_type, '测试报告')}"
        story.append(Paragraph(title, self.styles['CustomTitle']))

        subtitle = self.report_data.get('execution_details', {}).get('task_description') or '自动生成执行报告'
        story.append(Paragraph(subtitle, self.styles['CustomSmall']))
        story.append(Spacer(1, 0.2*cm))

        # 执行详情
        overview = self.report_data.get('overview', {})
        execution_details = self.report_data.get('execution_details', {})

        # 创建执行信息表格
        info_data = [
            ['用例名称', execution_details.get('case_name', 'N/A')],
            ['执行状态', overview.get('status', 'N/A')],
            ['执行模式', execution_details.get('execution_mode', 'N/A')],
            ['执行时长', overview.get('duration_formatted', 'N/A')],
            ['完成率', f"{overview.get('completion_rate', 0)}%"],
            ['生成时间', datetime.now().strftime('%Y-%m-%d %H:%M:%S')],
        ]

        info_table = self._build_table(
            info_data,
            col_widths=[5*cm, 10*cm],
            header_rows=0,
            body_first_col_background=self.theme['accent_soft']
        )
        story.append(info_table)
        story.append(Spacer(1, 0.5*cm))

        return story

    def _build_summary_report(self):
        """构建摘要报告"""
        story = []

        # 任务统计
        story.append(Paragraph('任务统计', self.styles['CustomHeading2']))

        statistics = self.report_data.get('statistics', {})
        if statistics:
            stats_data = [
                ['统计项', '数量'],
                ['总任务数', str(statistics.get('total', 0))],
                ['已完成', str(statistics.get('completed', 0))],
                ['待执行', str(statistics.get('pending', 0))],
                ['失败', str(statistics.get('failed', 0))],
                ['跳过', str(statistics.get('skipped', 0))],
            ]

            stats_table = self._build_table(
                stats_data,
                col_widths=[8*cm, 7*cm],
                header_rows=1,
                body_first_col_background=self.theme['accent_soft'],
                center_columns=[1]
            )
            story.append(stats_table)
            story.append(Spacer(1, 0.5*cm))

        # 任务时间线
        story.append(Paragraph('任务执行时间线', self.styles['CustomHeading2']))

        timeline = self.report_data.get('timeline', [])
        if timeline:
            timeline_data = [['任务ID', '描述', '状态']]
            for task in timeline:
                status_display = task.get('status_display', 'N/A')
                timeline_data.append([
                    f"任务 {task.get('id', 'N/A')}",
                    task.get('description', 'N/A'),
                    status_display
                ])

            timeline_table = self._build_table(
                timeline_data,
                col_widths=[2.5*cm, 8*cm, 4.5*cm],
                header_rows=1
            )
            story.append(timeline_table)

        # 添加性能分析摘要（如果数据可用）
        self._add_performance_summary(story)

        return story

    def _add_performance_summary(self, story):
        """添加性能分析摘要到报告"""
        # 检查是否有性能数据
        metrics = self.report_data.get('metrics')
        action_distribution = self.report_data.get('action_distribution')

        if not metrics and not action_distribution:
            return

        story.append(Spacer(1, 0.5*cm))
        story.append(Paragraph('性能摘要', self.styles['CustomHeading2']))

        # 性能指标
        if metrics:
            perf_data = [
                ['指标', '值'],
                ['总步骤数', str(metrics.get('total_steps', 0))],
                ['平均耗时', f"{metrics.get('avg_step_duration', 0)} 秒"],
                ['最长耗时', f"{metrics.get('max_step_duration', 0)} 秒"],
                ['最短耗时', f"{metrics.get('min_step_duration', 0)} 秒"],
            ]

            perf_table = self._build_table(
                perf_data,
                col_widths=[8*cm, 7*cm],
                header_rows=1,
                body_first_col_background=colors.HexColor('#edf9f2'),
                center_columns=[1]
            )
            story.append(perf_table)
            story.append(Spacer(1, 0.3*cm))

        # 操作类型分布（简要）
        if action_distribution:
            action_names = {
                'click': '点击',
                'input': '输入',
                'scroll': '滚动',
                'wait': '等待',
                'switch_tab': '切换标签',
                'navigate': '导航',
                'open_tab': '新标签',
                'done': '完成',
                'other': '其他'
            }

            distribution_data = [['操作', '次数']]
            for key, name in action_names.items():
                count = action_distribution.get(key, 0)
                if count > 0:
                    distribution_data.append([name, str(count)])

            if len(distribution_data) > 1:
                distribution_table = self._build_table(
                    distribution_data,
                    col_widths=[8*cm, 7*cm],
                    header_rows=1,
                    body_first_col_background=colors.HexColor('#edf9f2'),
                    center_columns=[1]
                )
                story.append(distribution_table)

    def _build_detailed_report(self):
        """构建详细步骤报告"""
        story = []

        # 执行步骤详情
        story.append(Paragraph('执行步骤详情', self.styles['CustomHeading2']))

        detailed_steps = self.report_data.get('detailed_steps', [])
        if detailed_steps:
            for step in detailed_steps:
                # 步骤标题
                step_header = f"步骤 {step.get('step_number', 'N/A')}"
                story.append(Paragraph(step_header, self.styles['CustomHeading3']))

                # 步骤内容
                step_data = [
                    ['操作', step.get('action', 'N/A')],
                    ['元素', step.get('element', '-')],
                    ['状态', step.get('status', 'N/A')],
                ]

                # 如果有思考过程，添加到表格中
                thinking = step.get('thinking', '')
                if thinking:
                    step_data.append(['思考', thinking])

                step_table = self._build_table(
                    step_data,
                    col_widths=[3*cm, 12*cm],
                    header_rows=0,
                    body_first_col_background=self.theme['accent_soft']
                )
                story.append(step_table)
                story.append(Spacer(1, 0.3*cm))

        # 错误信息
        errors = self.report_data.get('errors', [])
        if errors:
            story.append(Paragraph('错误信息', self.styles['CustomHeading2']))
            for error in errors:
                error_style = ParagraphStyle(
                    'ErrorStyle',
                    parent=self.styles['CustomNormal'],
                    textColor=colors.red,
                    fontName=self.font_name
                )
                story.append(Paragraph(f"• {error.get('message', 'Unknown error')}", error_style))

        return story

    def _build_performance_report(self):
        """构建性能分析报告"""
        story = []

        # 性能指标
        story.append(Paragraph('性能指标', self.styles['CustomHeading2']))

        metrics = self.report_data.get('metrics', {})
        if metrics:
            metrics_data = [
                ['指标', '值'],
                ['总步骤数', str(metrics.get('total_steps', 0))],
                ['平均步骤耗时', f"{metrics.get('avg_step_duration', 0)} 秒"],
                ['最长步骤耗时', f"{metrics.get('max_step_duration', 0)} 秒"],
                ['最短步骤耗时', f"{metrics.get('min_step_duration', 0)} 秒"],
            ]

            metrics_table = self._build_table(
                metrics_data,
                col_widths=[8*cm, 7*cm],
                header_rows=1,
                body_first_col_background=self.theme['accent_soft'],
                center_columns=[1]
            )
            story.append(metrics_table)
            story.append(Spacer(1, 0.5*cm))

        # 操作类型分布
        story.append(Paragraph('操作类型分布', self.styles['CustomHeading2']))

        action_distribution = self.report_data.get('action_distribution', {})
        if action_distribution:
            action_names = {
                'click': '点击',
                'input': '输入',
                'scroll': '滚动',
                'wait': '等待',
                'switch_tab': '切换标签',
                'navigate': '导航',
                'open_tab': '新标签',
                'done': '任务完成',
                'other': '其他'
            }

            distribution_data = [['操作类型', '次数']]
            for key, name in action_names.items():
                count = action_distribution.get(key, 0)
                if count > 0:
                    distribution_data.append([name, str(count)])

            distribution_table = self._build_table(
                distribution_data,
                col_widths=[8*cm, 7*cm],
                header_rows=1,
                body_first_col_background=self.theme['accent_soft'],
                center_columns=[1]
            )
            story.append(distribution_table)
            story.append(Spacer(1, 0.5*cm))

        # 性能瓶颈
        bottlenecks = self.report_data.get('bottlenecks', [])
        if bottlenecks:
            story.append(Paragraph('性能瓶颈', self.styles['CustomHeading2']))

            bottleneck_data = [['步骤', '操作', '耗时(秒)', '慢于平均']]
            for bn in bottlenecks:
                bottleneck_data.append([
                    f"步骤 {bn.get('step_number', 'N/A')}",
                    bn.get('action', 'N/A'),
                    str(bn.get('duration', 0)),
                    f"{bn.get('slower_than_avg_by', 0)}%"
                ])

            bottleneck_table = self._build_table(
                bottleneck_data,
                col_widths=[2*cm, 8*cm, 3*cm, 2*cm],
                header_rows=1,
                center_columns=[2, 3]
            )
            story.append(bottleneck_table)
            story.append(Spacer(1, 0.5*cm))

        # 优化建议
        recommendations = self.report_data.get('recommendations', [])
        if recommendations:
            story.append(Paragraph('优化建议', self.styles['CustomHeading2']))
            for i, rec in enumerate(recommendations, 1):
                story.append(Paragraph(f"{i}. {rec}", self.styles['CustomNormal']))

        return story
