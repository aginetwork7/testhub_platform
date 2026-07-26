# API Automation Test Assets

This directory is the TestHub-owned source of API automation test assets.

- Keep the original pytest directory structure under `tests/`.
- Add or update API automation tests here, not in the external reference repository.
- Keep endpoint aliases in `config/api_paths.json` and WebSocket parameters in `src/data/params.py`.
- Update `config/schemas/swagger.json` when the API contract changes, then run `python manage.py generate_api_automation_paths`.
- Run `python manage.py import_pyapitest_cases` after changing assets to synchronize TestHub metadata.
- Maintain multi-environment settings in `config/config.yaml` and `config/environments/.env.*`, then run `python manage.py sync_api_automation_environments --project <project-id>`.
- The Runner materializes these assets into isolated pytest modules during execution.