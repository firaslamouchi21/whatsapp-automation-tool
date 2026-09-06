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

    def test_non_mapping_file_rejected(self, tmp_path):
        bad = tmp_path / "list.yaml"
        bad.write_text("- one\n- two\n")
        with pytest.raises(TemplateError):
            self.manager.load_templates_from_file(bad)

    def test_malformed_entries_are_skipped(self, tmp_path):
        f = tmp_path / "mixed.yaml"
        f.write_text(
            "good:\n  name: Good\n  template: 'Hi {business_name}'\n"
            "  variables: [business_name]\n  language: en\n"
            "junk: not-a-dict\n"
        )
        self.manager.load_templates_from_file(f)
        assert "good" in self.manager.templates
        assert "junk" not in self.manager.templates

    def test_empty_file_is_noop(self, tmp_path):
        f = tmp_path / "empty.yaml"
        f.write_text("")
        self.manager.load_templates_from_file(f)  # must not raise
