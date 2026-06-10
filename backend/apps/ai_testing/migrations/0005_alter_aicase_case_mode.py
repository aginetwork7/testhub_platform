from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ai_testing', '0004_planner_v2_foundation'),
    ]

    operations = [
        migrations.AlterField(
            model_name='aicase',
            name='case_mode',
            field=models.CharField(
                choices=[('freeform', '自由描述'), ('hybrid', '混合步骤'), ('structured', '结构化步骤')],
                default='freeform',
                max_length=20,
                verbose_name='用例模式',
            ),
        ),
    ]