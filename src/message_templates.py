import json
from pathlib import Path
from typing import Any, Dict, Optional, cast

import yaml  # type: ignore


class TemplateError(Exception):
    pass


class MessageTemplateManager:

    def __init__(self, templates_dir: Optional[Path] = None):
        self.templates_dir = templates_dir or Path("templates")
        self.templates: Dict[str, Dict[str, Any]] = {}
        self._load_all_templates()

    def _load_all_templates(self) -> None:
        if not self.templates_dir.exists():
            self.templates_dir = Path(__file__).parent.parent / "templates"

        if not self.templates_dir.exists():
            return

        for yaml_file in self.templates_dir.rglob("*.yaml"):
            try:
                self.load_templates_from_file(yaml_file)
            except TemplateError:
                continue

        for json_file in self.templates_dir.rglob("*.json"):
            try:
                self.load_templates_from_file(json_file)
            except TemplateError:
                continue

    def load_templates_from_file(self, file_path: Path) -> None:
        if not file_path.exists():
            raise TemplateError(f"Template file not found: {file_path}")

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                if file_path.suffix.lower() in [".yaml", ".yml"]:
                    templates = yaml.safe_load(f)
                else:
                    templates = json.load(f)
        except (json.JSONDecodeError, yaml.YAMLError) as e:
            raise TemplateError(f"Error parsing template file: {e}")
        except Exception as e:
            raise TemplateError(f"Error loading template file: {e}")

        if templates is None:
            return
        if not isinstance(templates, dict):
            raise TemplateError(f"Template file must contain a mapping: {file_path}")

        for name, data in templates.items():
            if isinstance(data, dict) and "template" in data:
                self.templates[str(name)] = data

    def get_template(self, template_name: str) -> Optional[Dict[str, Any]]:
        return self.templates.get(template_name)

    def render_template(self, template_name: str, variables: Dict[str, Any]) -> str:
        template_data = self.get_template(template_name)
        if not template_data:
            raise TemplateError(f"Template not found: {template_name}")

        template_text = template_data["template"]
        if not isinstance(template_text, str):
            raise TemplateError(f"Invalid template format for: {template_name}")
        try:
            return cast(str, template_text.format_map(variables))
        except KeyError as e:
            raise TemplateError(f"Missing variable in template: {e}")

    def list_templates(self) -> Dict[str, str]:
        return {name: data.get("name", name) for name, data in self.templates.items()}

    def validate_template(self, template_name: str) -> bool:
        template = self.get_template(template_name)
        if not template:
            return False

        required_fields = ["name", "template", "variables", "language"]
        return all(field in template for field in required_fields)
