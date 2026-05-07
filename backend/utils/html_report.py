"""
通用HTML测试报告生成器，支持所有测试类型（UI/API/APP）
"""
import time
from datetime import datetime
from typing import Dict, List, Any, Optional


class HTMLReportGenerator:
    """HTML测试报告生成器"""
    
    def __init__(self):
        self.report_time = datetime.now()
    
    def generate_report(
        self,
        title: str,
        test_type: str,
        summary: Dict[str, Any],
        test_cases: List[Dict[str, Any]],
        environment: Optional[Dict[str, str]] = None,
        report_url: Optional[str] = None,
        execution_time: Optional[str] = None
    ) -> str:
        """生成HTML测试报告
        
        Args:
            title: 报告标题
            test_type: 测试类型（UI自动化测试/API测试/APP自动化测试）
            summary: 测试摘要信息
                - total: 总用例数
                - passed: 通过数
                - failed: 失败数
                - skipped: 跳过数
                - error: 错误数
                - duration: 执行时长（秒）
            test_cases: 测试用例列表
                - name: 用例名称
                - status: 状态（passed/failed/skipped/error）
                - duration: 执行时长
                - error_message: 错误信息（可选）
            environment: 环境信息（可选）
            report_url: 完整报告链接（可选）
            execution_time: 执行时间（可选）
        
        Returns:
            str: HTML报告内容
        """
        pass_rate = self._calculate_pass_rate(summary)
        status_color = self._get_status_color(pass_rate)
        
        # 使用传入的执行时间，如果没有则使用当前时间
        display_time = execution_time if execution_time else self.report_time.strftime('%Y-%m-%d %H:%M:%S')
        
        html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - 测试报告</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #f5f7fa; color: #333; line-height: 1.6; }}
        .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
        .header {{ background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); color: white; padding: 30px; border-radius: 10px; margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
        .header h1 {{ font-size: 24px; margin-bottom: 10px; }}
        .header .meta {{ font-size: 14px; opacity: 0.9; }}
        .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 20px; }}
        .summary-card {{ background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); text-align: center; }}
        .summary-card .number {{ font-size: 36px; font-weight: bold; margin-bottom: 5px; }}
        .summary-card .label {{ font-size: 14px; color: #666; }}
        .summary-card.total .number {{ color: #409eff; }}
        .summary-card.passed .number {{ color: #67c23a; }}
        .summary-card.failed .number {{ color: #f56c6c; }}
        .summary-card.skipped .number {{ color: #e6a23c; }}
        .summary-card.error .number {{ color: #f56c6c; }}
        .summary-card.rate .number {{ color: {status_color}; }}
        .progress-container {{ background: white; padding: 20px; border-radius: 10px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }}
        .progress-bar {{ height: 20px; background: #e9ecef; border-radius: 10px; overflow: hidden; display: flex; }}
        .progress-bar .passed {{ background: #67c23a; height: 100%; }}
        .progress-bar .failed {{ background: #f56c6c; height: 100%; }}
        .progress-bar .skipped {{ background: #e6a23c; height: 100%; }}
        .progress-bar .error {{ background: #909399; height: 100%; }}
        .progress-legend {{ display: flex; justify-content: center; gap: 20px; margin-top: 10px; font-size: 14px; }}
        .progress-legend span {{ display: flex; align-items: center; gap: 5px; }}
        .progress-legend .dot {{ width: 12px; height: 12px; border-radius: 50%; }}
        .section {{ background: white; border-radius: 10px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); overflow: hidden; }}
        .section-header {{ padding: 15px 20px; border-bottom: 1px solid #e9ecef; font-weight: bold; display: flex; justify-content: space-between; align-items: center; }}
        .section-content {{ padding: 20px; }}
        .test-case {{ border: 1px solid #e9ecef; border-radius: 8px; margin-bottom: 10px; overflow: hidden; }}
        .test-case-header {{ padding: 12px 15px; display: flex; justify-content: space-between; align-items: center; cursor: pointer; background: #fafafa; }}
        .test-case-header:hover {{ background: #f0f0f0; }}
        .test-case-name {{ font-weight: 500; }}
        .test-case-meta {{ display: flex; align-items: center; gap: 15px; font-size: 13px; color: #666; }}
        .status-badge {{ padding: 3px 10px; border-radius: 12px; font-size: 12px; font-weight: 500; }}
        .status-badge.passed {{ background: #f0f9eb; color: #67c23a; }}
        .status-badge.failed {{ background: #fef0f0; color: #f56c6c; }}
        .status-badge.skipped {{ background: #fdf6ec; color: #e6a23c; }}
        .status-badge.error {{ background: #f4f4f5; color: #909399; }}
        .test-case-detail {{ padding: 15px; background: #fafafa; border-top: 1px solid #e9ecef; display: none; }}
        .test-case-detail.show {{ display: block; }}
        .error-message {{ background: #fef0f0; border: 1px solid #fde2e2; border-radius: 4px; padding: 10px; font-family: monospace; font-size: 13px; white-space: pre-wrap; word-break: break-all; color: #f56c6c; }}
        .environment-table {{ width: 100%; border-collapse: collapse; }}
        .environment-table td {{ padding: 10px; border-bottom: 1px solid #e9ecef; }}
        .environment-table td:first-child {{ width: 150px; font-weight: 500; color: #666; }}
        .report-link {{ display: inline-block; background: #409eff; color: white; padding: 10px 20px; border-radius: 5px; text-decoration: none; margin-top: 10px; }}
        .report-link:hover {{ background: #66b1ff; }}
        .footer {{ text-align: center; padding: 20px; color: #999; font-size: 13px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{title}</h1>
            <div class="meta">
                <span>测试类型: {test_type}</span> | 
                <span>执行时间: {display_time}</span> |
                <span>执行时长: {self._format_duration(summary.get('duration', 0))}</span>
            </div>
        </div>
        
        <div class="summary">
            <div class="summary-card total">
                <div class="number">{summary.get('total', 0)}</div>
                <div class="label">总用例数</div>
            </div>
            <div class="summary-card passed">
                <div class="number">{summary.get('passed', 0)}</div>
                <div class="label">通过</div>
            </div>
            <div class="summary-card failed">
                <div class="number">{summary.get('failed', 0)}</div>
                <div class="label">失败</div>
            </div>
            <div class="summary-card skipped">
                <div class="number">{summary.get('skipped', 0)}</div>
                <div class="label">跳过</div>
            </div>
            <div class="summary-card rate">
                <div class="number">{pass_rate:.1f}%</div>
                <div class="label">通过率</div>
            </div>
        </div>
        
        <div class="progress-container">
            <div class="progress-bar">
                {self._generate_progress_bar(summary)}
            </div>
            <div class="progress-legend">
                <span><div class="dot" style="background: #67c23a;"></div>通过 {summary.get('passed', 0)}</span>
                <span><div class="dot" style="background: #f56c6c;"></div>失败 {summary.get('failed', 0)}</span>
                <span><div class="dot" style="background: #e6a23c;"></div>跳过 {summary.get('skipped', 0)}</span>
            </div>
        </div>
        
        {self._generate_environment_section(environment)}
        
        <div class="section">
            <div class="section-header">
                <span>测试用例详情</span>
                <span>{len(test_cases)} 个用例</span>
            </div>
            <div class="section-content">
                {self._generate_test_cases(test_cases)}
            </div>
        </div>
        
        {self._generate_report_link_section(report_url)}
        
        <div class="footer">
            <p>此报告由 TestHub 平台自动生成 | 生成时间: {self.report_time.strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>
    </div>
    <script>
        document.querySelectorAll('.test-case-header').forEach(header => {{
            header.addEventListener('click', function() {{
                const detail = this.nextElementSibling;
                detail.classList.toggle('show');
            }});
        }});
    </script>
</body>
</html>'''
        return html
    
    def _calculate_pass_rate(self, summary: Dict[str, Any]) -> float:
        """计算通过率"""
        total = summary.get('total', 0)
        if total == 0:
            return 0.0
        passed = summary.get('passed', 0)
        return (passed / total) * 100
    
    def _get_status_color(self, pass_rate: float) -> str:
        """根据通过率获取状态颜色"""
        if pass_rate >= 80:
            return '#67c23a'
        elif pass_rate >= 60:
            return '#e6a23c'
        else:
            return '#f56c6c'
    
    def _format_duration(self, seconds: float) -> str:
        """格式化执行时长"""
        if seconds < 60:
            return f'{seconds:.2f}秒'
        elif seconds < 3600:
            minutes = int(seconds // 60)
            secs = int(seconds % 60)
            return f'{minutes}分{secs}秒'
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f'{hours}小时{minutes}分'
    
    def _generate_progress_bar(self, summary: Dict[str, Any]) -> str:
        """生成进度条"""
        total = summary.get('total', 0)
        if total == 0:
            return ''
        
        passed = summary.get('passed', 0)
        failed = summary.get('failed', 0)
        skipped = summary.get('skipped', 0)
        
        passed_width = (passed / total) * 100
        failed_width = (failed / total) * 100
        skipped_width = (skipped / total) * 100
        
        return f'''
            <div class="passed" style="width: {passed_width}%;"></div>
            <div class="failed" style="width: {failed_width}%;"></div>
            <div class="skipped" style="width: {skipped_width}%;"></div>
        '''
    
    def _generate_environment_section(self, environment: Optional[Dict[str, str]]) -> str:
        """生成环境信息部分"""
        if not environment:
            return ''
        
        rows = ''
        for key, value in environment.items():
            rows += f'<tr><td>{key}</td><td>{value}</td></tr>'
        
        return f'''
        <div class="section">
            <div class="section-header">
                <span>测试环境</span>
            </div>
            <div class="section-content">
                <table class="environment-table">
                    {rows}
                </table>
            </div>
        </div>
        '''
    
    def _generate_test_cases(self, test_cases: List[Dict[str, Any]]) -> str:
        """生成测试用例列表"""
        if not test_cases:
            return '<p style="text-align: center; color: #999;">暂无测试用例</p>'
        
        html = ''
        for i, case in enumerate(test_cases):
            status = case.get('status', 'unknown')
            status_text = {'passed': '通过', 'failed': '失败', 'skipped': '跳过', 'error': '错误'}.get(status, status)
            duration = case.get('duration', 0)
            error_message = case.get('error_message', '')
            
            detail_html = ''
            if error_message:
                detail_html = f'''
                <div class="test-case-detail">
                    <div class="error-message">{error_message}</div>
                </div>
                '''
            else:
                detail_html = '<div class="test-case-detail"></div>'
            
            html += f'''
            <div class="test-case">
                <div class="test-case-header">
                    <span class="test-case-name">{case.get('name', f'用例{i+1}')}</span>
                    <div class="test-case-meta">
                        <span>{self._format_duration(duration)}</span>
                        <span class="status-badge {status}">{status_text}</span>
                    </div>
                </div>
                {detail_html}
            </div>
            '''
        
        return html
    
    def _generate_report_link_section(self, report_url: Optional[str]) -> str:
        """生成报告链接部分"""
        if not report_url:
            return ''
        
        return f'''
        <div class="section">
            <div class="section-header">
                <span>完整报告</span>
            </div>
            <div class="section-content" style="text-align: center;">
                <p>点击下方链接查看完整的测试报告（包含截图、录屏等详细信息）</p>
                <a href="{report_url}" class="report-link" target="_blank">查看完整报告</a>
            </div>
        </div>
        '''
    
    def generate_simple_report(
        self,
        title: str,
        test_type: str,
        total: int,
        passed: int,
        failed: int,
        skipped: int = 0,
        duration: float = 0,
        report_url: Optional[str] = None
    ) -> str:
        """生成简化版HTML测试报告
        
        Args:
            title: 报告标题
            test_type: 测试类型
            total: 总用例数
            passed: 通过数
            failed: 失败数
            skipped: 跳过数
            duration: 执行时长（秒）
            report_url: 完整报告链接（可选）
        
        Returns:
            str: HTML报告内容
        """
        summary = {
            'total': total,
            'passed': passed,
            'failed': failed,
            'skipped': skipped,
            'duration': duration
        }
        
        test_cases = []
        for i in range(failed):
            test_cases.append({
                'name': f'失败用例 #{i+1}',
                'status': 'failed',
                'duration': 0,
                'error_message': '执行失败'
            })
        
        return self.generate_report(
            title=title,
            test_type=test_type,
            summary=summary,
            test_cases=test_cases,
            report_url=report_url
        )


html_report_generator = HTMLReportGenerator()
