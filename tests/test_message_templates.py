from pathlib import Path

import pytest

from src.message_templates import MessageTemplateManager, TemplateError


class TestMessageTemplateManager:

    def setup_method(self):
        self.manager = MessageTemplateManager()

    def test_default_templates_loaded(self):
        templates = self.manager.list_templates()
        # Templates ship per language under templates/<lang>/<category>/messages.yaml
        assert "meeting_request" in templates
        assert "meeting_request_ar" in templates

    def test_get_template(self):
        template = self.manager.get_template("meeting_request")
        assert template is not None
        assert "template" in template
        assert "variables" in template
        assert "language" in template

    def test_get_nonexistent_template(self):
        template = self.manager.get_template("nonexistent")
        assert template is None

    def test_render_template(self):
        message = self.manager.render_template(
            "meeting_request", {"business_name": "Test Business"}
        )
        assert "Test Business" in message

    def test_render_template_missing_variable(self):
        with pytest.raises(TemplateError):
            self.manager.render_template("meeting_request", {})

    def test_validate_template(self):
        assert self.manager.validate_template("meeting_request")
        assert not self.manager.validate_template("nonexistent")

    def test_load_templates_from_file(self, tmp_path):
        templates_file = tmp_path / "templates.json"
        templates_file.write_text("""
        {
            "test_template": {
                "name": "Test Template",
                "template": "Hello {name}",
                "variables": ["name"],
                "language": "en"
            }
        }
        """)

        self.manager.load_templates_from_file(templates_file)
        assert "test_template" in self.manager.list_templates()

    def test_load_invalid_file(self, tmp_path):
        invalid_file = tmp_path / "invalid.json"
        invalid_file.write_text("invalid json")

        with pytest.raises(TemplateError):
            self.manager.load_templates_from_file(invalid_file)
