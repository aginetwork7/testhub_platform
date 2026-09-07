from django.db import migrations


PLANNER_VISION_PROMPT = """Choose one action for the supplied current-page observation. Treat the accessibility tree as the primary semantic view, actionable controls as the executable locator inventory, and the screenshot as fallback evidence for unresolved visual ambiguity.

Apply a single-step observe-reason-act-verify loop:
- Make implicit transitions explicit. If the target is behind a menu, dialog, tab, or collapsed region, choose only the discovered control that reveals the next state, then observe again.
- Resolve blocking state first. When a blocking layer is present, operate one discovered control within that layer before any background target.
- Treat every state-changing action as unverified until its required assertion passes. When an action completes but verification fails, use the new observation to choose a distinct discovered action.
- If the required state is already objectively observable, submit an assert action immediately with complete bindings for bindable assertions.
- Fail closed on ambiguity. Do not choose among multiple semantic matches and do not invent a selector; use a discovered action that can disambiguate the state, or allow validation to reject the plan.

Never return coordinates, fixed application selectors, multiple actions, business-specific fallback flows, or assertions unsupported by current evidence."""


def update_default_planner_vision_prompt(apps, schema_editor):
    Prompt = apps.get_model('ai_testing', 'AITestPromptConfig')
    Prompt.objects.filter(
        prompt_type='planner_vision',
        name='Planner Vision 默认提示词',
    ).update(content=PLANNER_VISION_PROMPT)


class Migration(migrations.Migration):
    dependencies = [('ai_testing', '0026_seed_planner_text_prompt')]
    operations = [
        migrations.RunPython(update_default_planner_vision_prompt, migrations.RunPython.noop),
    ]