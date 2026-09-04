from django.db import migrations


PLANNER_TEXT_PROMPT = """You are a test planner. Produce a minimal, ordered JSON plan for the requested test goal. Use only declared generic capabilities, require evidence-backed assertions, and never infer credentials, fixed selectors, coordinates, page names, or business-specific fallback flows."""


def seed_planner_text_prompt(apps, schema_editor):
    Prompt = apps.get_model('ai_testing', 'AITestPromptConfig')
    if not Prompt.objects.filter(prompt_type='planner_text', is_active=True).exists():
        Prompt.objects.create(
            name='Planner Text 默认提示词',
            prompt_type='planner_text',
            content=PLANNER_TEXT_PROMPT,
            is_active=True,
        )


class Migration(migrations.Migration):
    dependencies = [('ai_testing', '0025_remove_aicase_environment_configuration')]
    operations = [migrations.RunPython(seed_planner_text_prompt, migrations.RunPython.noop)]