"""被计划契约拒绝时，给模型附上一个最小合规示例。

规划模型生成的计划被服务端契约校验拒绝后，重试消息此前只重复一遍违规文本，模型没有可照抄的正确形态。
冷启动实测中出现过同一条校验连续五次被拒、整个用例在一步浏览器操作都没执行的情况下就判失败。
按拒绝类型附上一个可直接照抄的合规步骤，能让下一次尝试改对具体的那一处。

示例本身必须能通过 `GlobalTestPlanner.normalize_response`，`tests/test_plan_contract_examples.py`
会逐条回放校验，防止示例自身失效后误导模型。
"""

from __future__ import annotations

import json
from typing import Any

# 每条规则由「命中标记」与「示例步骤」组成。标记取自校验抛出的错误文本，中英文都列出是因为
# 现有校验的措辞两种都有。顺序即匹配优先级，先写更具体的规则。
_RULES: tuple[tuple[tuple[str, ...], str, list[dict[str, Any]]], ...] = (
    (
        ('cannot assert a committed selected value before the transaction dialog is confirmed',),
        '选择打开了事务对话框时，先断言对话框出现，把已提交值的断言放到确认那一步',
        [
            {
                'executor': 'browser',
                'allowed_capabilities': ['browser.act', 'browser.inspect'],
                'description': "Select the 'Approved' option from the Action dropdown.",
                'transition': {'kind': 'select_option', 'value': 'Approved'},
                'assertions': [
                    {
                        'action': 'assert',
                        'assert_kind': 'popup',
                        'operator': 'exists',
                        'expected': {'value': True},
                        'target': {'intent': 'reason dialog opened by choosing Approved'},
                        'required': True,
                    },
                ],
            },
            {
                'executor': 'browser',
                'allowed_capabilities': ['browser.act', 'browser.inspect'],
                'description': 'Click Confirm in the dialog to commit the Approved selection.',
                'transition': {'kind': 'generic'},
                'assertions': [
                    {
                        'action': 'assert',
                        'assert_kind': 'field_value',
                        'operator': 'starts_with',
                        'expected': {'value': 'Approved'},
                        'target': {'intent': 'Action dropdown showing the committed selected value'},
                        'required': True,
                    },
                ],
            },
        ],
    ),
    (
        ('选择下拉选项后未验证所选值', 'did not verify the selected value'),
        '选择下拉选项的步骤必须验证控件上显示出来的所选值',
        [
            {
                'executor': 'browser',
                'allowed_capabilities': ['browser.act', 'browser.inspect'],
                'description': "Select the 'Detailed View' option from the View mode dropdown.",
                'transition': {'kind': 'select_option', 'value': 'Detailed View'},
                'assertions': [
                    {
                        'action': 'assert',
                        'assert_kind': 'field_value',
                        'operator': 'starts_with',
                        'expected': {'value': 'Detailed View'},
                        'target': {'intent': 'View mode dropdown showing the committed selected value'},
                        'required': True,
                    },
                ],
            },
        ],
    ),
    (
        ('commits a transaction but only asserts that a layer disappeared',),
        '提交类步骤要断言提交后可见的结果，弹层消失只能作为附加断言',
        [
            {
                'executor': 'browser',
                'allowed_capabilities': ['browser.act', 'browser.inspect'],
                'description': 'Click Confirm in the dialog to commit the Approved selection.',
                'transition': {'kind': 'generic'},
                'assertions': [
                    {
                        'action': 'assert',
                        'assert_kind': 'field_value',
                        'operator': 'starts_with',
                        'expected': {'value': 'Approved'},
                        'target': {'intent': 'status control showing the committed value'},
                        'required': True,
                    },
                    {
                        'action': 'assert',
                        'assert_kind': 'popup',
                        'operator': 'not_exists',
                        'expected': {'value': True},
                        'target': {'intent': 'reason dialog that was confirmed'},
                        'required': False,
                    },
                ],
            },
        ],
    ),
    (
        ('不能用 absence 验证搜索结果不存在',),
        '验证搜索结果里不存在某个标识，用 text not_contains，不要用 absence',
        [
            {
                'executor': 'browser',
                'allowed_capabilities': ['browser.act', 'browser.inspect'],
                'description': 'Search for user@example.com in the left-side search box.',
                'transition': {'kind': 'filter_results', 'value': 'user@example.com', 'result_presence': 'absent'},
                'assertions': [
                    {
                        'action': 'assert',
                        'assert_kind': 'text',
                        'operator': 'not_contains',
                        'expected': {'value': 'user@example.com'},
                        'target': {'intent': 'search results area'},
                        'required': True,
                    },
                ],
            },
        ],
    ),
    (
        ('缺少结构化 transition', 'transition.kind 无效', 'transition.value 不能为空', 'result_presence 无效', 'transition 格式无效'),
        '每个浏览器步骤都要声明结构化 transition：普通转换用 generic，选择选项用 select_option 并带 value，筛选结果用 filter_results 并带 value 与 result_presence',
        [
            {
                'executor': 'browser',
                'allowed_capabilities': ['browser.act', 'browser.inspect'],
                'description': 'Click the Items icon to open the items list.',
                'transition': {'kind': 'generic'},
                'assertions': [
                    {
                        'action': 'assert',
                        'assert_kind': 'element_state',
                        'operator': 'exists',
                        'expected': {'value': True},
                        'target': {'intent': 'items list area'},
                        'required': True,
                    },
                ],
            },
            {
                'executor': 'browser',
                'allowed_capabilities': ['browser.act', 'browser.inspect'],
                'description': "Search for the site North District in the site search box.",
                'transition': {'kind': 'filter_results', 'value': 'North District', 'result_presence': 'present'},
                'assertions': [
                    {
                        'action': 'assert',
                        'assert_kind': 'collection',
                        'operator': 'greater_than',
                        'expected': {'value': 0},
                        'target': {'intent': 'site rows matching the searched site name'},
                        'required': True,
                    },
                ],
            },
        ],
    ),
    (
        ('contains a conditional branch',),
        '步骤描述不能含条件分支，只规划无条件必达的状态',
        [
            {
                'executor': 'browser',
                'allowed_capabilities': ['browser.act', 'browser.inspect'],
                'description': 'Click the media thumbnail to open its live view.',
                'transition': {'kind': 'generic'},
                'assertions': [
                    {
                        'action': 'assert',
                        'assert_kind': 'stream_state',
                        'operator': 'equals',
                        'expected': {'minimum_advanced_seconds': 1},
                        'target': {'intent': 'live video stream for the opened item'},
                        'required': True,
                    },
                ],
            },
        ],
    ),
    (
        ('禁止关闭验证', '必须包含非空 assertions', 'must declare at least one required assertion'),
        '每个浏览器步骤都必须带至少一条 required 断言，不能关闭验证',
        [
            {
                'executor': 'browser',
                'allowed_capabilities': ['browser.act', 'browser.inspect'],
                'description': 'Click the Records icon to open the record list.',
                'transition': {'kind': 'generic'},
                'assertions': [
                    {
                        'action': 'assert',
                        'assert_kind': 'collection',
                        'operator': 'greater_than',
                        'expected': {'value': 0},
                        'target': {'intent': 'record rows in the opened record list'},
                        'required': True,
                    },
                ],
            },
        ],
    ),
    (
        ('假设状态选择后才出现字段对话框',),
        '先设置并验证字段，再执行最终状态转换，不要把字段对话框安排在状态选择之后',
        [
            {
                'executor': 'browser',
                'allowed_capabilities': ['browser.act', 'browser.inspect'],
                'description': 'Select Other as the reason in the reason dialog.',
                'transition': {'kind': 'select_option', 'value': 'Other'},
                'assertions': [
                    {
                        'action': 'assert',
                        'assert_kind': 'field_value',
                        'operator': 'starts_with',
                        'expected': {'value': 'Other'},
                        'target': {'intent': 'reason field showing the chosen value'},
                        'required': True,
                    },
                ],
            },
            {
                'executor': 'browser',
                'allowed_capabilities': ['browser.act', 'browser.inspect'],
                'description': 'Click Confirm to commit the status change.',
                'transition': {'kind': 'generic'},
                'assertions': [
                    {
                        'action': 'assert',
                        'assert_kind': 'field_value',
                        'operator': 'starts_with',
                        'expected': {'value': 'Approved'},
                        'target': {'intent': 'status control showing the committed value'},
                        'required': True,
                    },
                ],
            },
        ],
    ),
    (
        ('visual_change cannot prove a semantic final state',),
        'visual_change 不能证明语义终态，改用对具体目标的断言',
        [
            {
                'executor': 'browser',
                'allowed_capabilities': ['browser.act', 'browser.inspect'],
                'description': 'Click the 10s Forward button on the playback page.',
                'transition': {'kind': 'generic'},
                'assertions': [
                    {
                        'action': 'assert',
                        'assert_kind': 'playback',
                        'operator': 'equals',
                        'expected': {'minimum_advanced_seconds': 10},
                        'target': {'intent': 'playback player for the opened item'},
                        'required': True,
                    },
                ],
            },
        ],
    ),
    (
        ('correlates_resource 未引用',),
        'correlates_resource 只能引用此前 data_factory 步骤创建的 resource_type',
        [
            {
                'executor': 'data_factory',
                'action': 'create',
                'allowed_capabilities': ['data_factory.create'],
                'description': 'Create one normal person alert event via the event construction tool.',
                'resource_type': 'alert_event',
                'arguments': {'alert_type': 'person'},
            },
            {
                'executor': 'browser',
                'allowed_capabilities': ['browser.act', 'browser.inspect'],
                'description': 'Click the first alert thumbnail in the alert list.',
                'transition': {'kind': 'generic'},
                'correlates_resource': 'alert_event',
                'assertions': [
                    {
                        'action': 'assert',
                        'assert_kind': 'element_state',
                        'operator': 'exists',
                        'expected': {'value': True},
                        'target': {'intent': 'alert detail panel for the opened alert'},
                        'required': True,
                    },
                ],
            },
        ],
    ),
)


def retry_guidance(error_message: object) -> str:
    """返回与该拒绝原因对应的合规示例，没有匹配规则时返回空串。"""
    text = str(error_message or '')
    if not text:
        return ''
    for markers, title, steps in _RULES:
        if any(marker in text for marker in markers):
            payload = json.dumps({'steps': steps}, ensure_ascii=False, indent=2)
            return (
                f'\n\n针对这一条违规的最小合规示例（{title}）。'
                '照抄其中的断言与 transition 形态，替换成本用例的实际控件与取值，不要照抄示例里的业务名词：\n'
                f'{payload}'
            )
    return ''


def example_steps_for(error_message: object) -> list[dict[str, Any]]:
    """返回该拒绝原因对应的示例步骤，供单元测试回放校验。"""
    text = str(error_message or '')
    for markers, _title, steps in _RULES:
        if any(marker in text for marker in markers):
            return [dict(step) for step in steps]
    return []


def all_rule_markers() -> list[str]:
    """每条规则的首个标记，供测试确认覆盖了哪些校验。"""
    return [markers[0] for markers, _title, _steps in _RULES]
