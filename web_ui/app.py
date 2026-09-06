import logging
import os
import re
import sys
import threading
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import yaml
from flask import Flask, jsonify, render_template, request, send_from_directory
from werkzeug.utils import secure_filename

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from config.settings import ConfigManager  # noqa: E402
from src.message_templates import MessageTemplateManager  # noqa: E402
from src.phone_validator import PhoneValidator  # noqa: E402
from src.whatsapp_automation import WhatsAppAutomation  # noqa: E402

# Directory that holds the message templates (templates/<lang>/<category>/messages.yaml).
# This is NOT Flask's own template dir (web_ui/templates), so it must be resolved
# explicitly against the project root regardless of the process working directory.
MESSAGE_TEMPLATES_DIR = PROJECT_ROOT / "templates"

_DEFAULT_SECRET = (
    "dev-secret-key-change-in-production"  # nosec B105 - placeholder, not a credential
)
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", _DEFAULT_SECRET)
if app.secret_key == _DEFAULT_SECRET:
    logging.getLogger("web_ui").warning(
        "SECRET_KEY is unset - using an insecure default. Set SECRET_KEY before exposing this."
    )

UPLOAD_FOLDER = PROJECT_ROOT / "data"
UPLOAD_FOLDER.mkdir(exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_HTTPONLY"] = True

ALLOWED_EXTENSIONS = {"csv", "xlsx", "xls"}
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


@app.before_request
def _reject_cross_origin_writes():
    """Lightweight CSRF guard for a same-origin JSON API. A state-changing request
    is allowed only if it carries a JSON body (which a cross-site page cannot send
    without a CORS preflight this app never answers) or a same-origin Origin/Referer.
    """
    if request.method in _SAFE_METHODS or app.config.get("TESTING"):
        return None
    content_type = (request.content_type or "").split(";")[0].strip()
    if content_type == "application/json":
        return None
    for header in ("Origin", "Referer"):
        value = request.headers.get(header)
        if value and urlparse(value).netloc == request.host:
            return None
    return jsonify({"error": "cross-origin request rejected"}), 403


template_manager = MessageTemplateManager(MESSAGE_TEMPLATES_DIR)
phone_validator = PhoneValidator()

campaign_state = {"selected_template": None, "leads_file": None, "leads_data": [], "status": "idle"}
# Serialises campaign start/progress updates - the state dict is a single shared object.
_state_lock = threading.Lock()


_SEGMENT_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _safe_template_dir(lang: str, category: str) -> Path:
    """Resolve templates/<lang>/<category>, rejecting anything that could escape
    the templates directory (path traversal via the language/category fields)."""
    if not (_SEGMENT_RE.match(lang or "") and _SEGMENT_RE.match(category or "")):
        raise ValueError("language and category must match [a-z0-9_-]")
    target = (MESSAGE_TEMPLATES_DIR / lang / category).resolve()
    if MESSAGE_TEMPLATES_DIR.resolve() not in target.parents:
        raise ValueError("resolved path escapes the templates directory")
    return target


@app.route("/")
def index():
    templates = template_manager.list_templates()
    return render_template("index.html", templates=templates, campaign=campaign_state)


@app.route("/api/templates")
def get_templates():
    # Full template objects keyed by id: the dashboard needs name/language/variables.
    return jsonify(template_manager.templates)


@app.route("/api/templates/<template_name>")
def get_template(template_name):
    template = template_manager.get_template(template_name)
    if template:
        return jsonify(template)
    return jsonify({"error": "Template not found"}), 404


@app.route("/api/templates", methods=["POST"])
def create_template():
    data = request.json

    required_fields = ["name", "template_id", "template_text", "variables", "language", "category"]
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Missing required field: {field}"}), 400

    lang = str(data["language"]).lower()
    category = str(data["category"]).lower()

    try:
        template_dir = _safe_template_dir(lang, category)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    template_dir.mkdir(parents=True, exist_ok=True)

    template_file = template_dir / "messages.yaml"

    templates = {}
    if template_file.exists():
        with open(template_file, "r", encoding="utf-8") as f:
            templates = yaml.safe_load(f) or {}

    templates[data["template_id"]] = {
        "name": data["name"],
        "subject": data.get("subject", ""),
        "template": data["template_text"],
        "variables": data["variables"],
        "language": lang,
    }

    with open(template_file, "w", encoding="utf-8") as f:
        yaml.dump(templates, f, allow_unicode=True, sort_keys=False)

    global template_manager
    template_manager = MessageTemplateManager(MESSAGE_TEMPLATES_DIR)

    return jsonify({"success": True, "message": "Template created successfully"})


@app.route("/api/templates/<template_name>", methods=["DELETE"])
def delete_template(template_name):
    templates_dir = MESSAGE_TEMPLATES_DIR

    for yaml_file in templates_dir.rglob("*.yaml"):
        try:
            with open(yaml_file, "r", encoding="utf-8") as f:
                templates = yaml.safe_load(f) or {}

            if template_name in templates:
                del templates[template_name]

                with open(yaml_file, "w", encoding="utf-8") as f:
                    yaml.dump(templates, f, allow_unicode=True, sort_keys=False)

                global template_manager
                template_manager = MessageTemplateManager(MESSAGE_TEMPLATES_DIR)

                return jsonify({"success": True, "message": "Template deleted"})
        except Exception:
            continue

    return jsonify({"error": "Template not found"}), 404


@app.route("/api/campaign/select-template", methods=["POST"])
def select_template():
    data = request.json
    template_name = data.get("template_name")

    template = template_manager.get_template(template_name)
    if not template:
        return jsonify({"error": "Template not found"}), 404

    campaign_state["selected_template"] = template_name
    campaign_state["status"] = "template_selected"

    return jsonify(
        {"success": True, "template": template, "campaign_status": campaign_state["status"]}
    )


@app.route("/api/leads/upload", methods=["POST"])
def upload_leads():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    if file and allowed_file(file.filename):
        filename = secure_filename(f"leads_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
        filepath = UPLOAD_FOLDER / filename
        file.save(filepath)

        try:
            df = pd.read_csv(filepath)

            required = ["Business Name", "Phone Number"]
            missing = [col for col in required if col not in df.columns]

            if missing:
                return jsonify({"error": f"Missing columns: {missing}"}), 400

            valid_leads = []
            invalid_count = 0

            for _, row in df.iterrows():
                phone = str(row.get("Phone Number", ""))
                formatted = phone_validator.validate_and_format(phone)

                if formatted:
                    valid_leads.append(
                        {
                            "business_name": str(row.get("Business Name", "")),
                            "phone_number": formatted,
                            "category": str(row.get("Category", "")),
                            "original_data": row.to_dict(),
                        }
                    )
                else:
                    invalid_count += 1

            campaign_state["leads_file"] = str(filepath)
            campaign_state["leads_data"] = valid_leads
            campaign_state["status"] = "leads_loaded"

            return jsonify(
                {
                    "success": True,
                    "leads_count": len(valid_leads),
                    "invalid_count": invalid_count,
                    "preview": valid_leads[:5],
                }
            )

        except Exception as e:
            return jsonify({"error": f"Error processing file: {str(e)}"}), 400

    return jsonify({"error": "Invalid file type"}), 400


@app.route("/api/leads/add", methods=["POST"])
def add_lead():
    data = request.json

    business_name = data.get("business_name", "").strip()
    phone_number = data.get("phone_number", "").strip()
    category = data.get("category", "").strip()

    if not business_name or not phone_number:
        return jsonify({"error": "Business name and phone number are required"}), 400

    # Validate phone
    formatted = phone_validator.validate_and_format(phone_number)
    if not formatted:
        return jsonify({"error": "Invalid phone number"}), 400

    lead = {
        "business_name": business_name,
        "phone_number": formatted,
        "category": category,
        "original_data": data,
    }

    campaign_state["leads_data"].append(lead)
    campaign_state["status"] = "leads_loaded"

    return jsonify(
        {"success": True, "lead": lead, "total_leads": len(campaign_state["leads_data"])}
    )


@app.route("/api/leads/clear", methods=["POST"])
def clear_leads():
    campaign_state["leads_data"] = []
    campaign_state["leads_file"] = None
    if campaign_state["status"] == "leads_loaded":
        campaign_state["status"] = "template_selected"

    return jsonify({"success": True, "message": "Leads cleared"})


@app.route("/api/campaign/preview", methods=["POST"])
def preview_message():
    data = request.json
    template_name = data.get("template")
    lead = data.get("lead", {})

    if not template_name:
        return jsonify({"error": "Template name required"}), 400

    try:
        message = template_manager.render_template(template_name, lead)
        return jsonify({"success": True, "message": message})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/campaign/confirm", methods=["POST"])
def confirm_campaign():
    if not campaign_state["selected_template"]:
        return jsonify({"error": "No template selected"}), 400

    if not campaign_state["leads_data"]:
        return jsonify({"error": "No leads loaded"}), 400

    campaign_state["status"] = "confirmed"

    template = template_manager.get_template(campaign_state["selected_template"])

    preview = None
    if campaign_state["leads_data"]:
        try:
            preview = template_manager.render_template(
                campaign_state["selected_template"], campaign_state["leads_data"][0]
            )
        except Exception as e:
            preview = f"Error generating preview: {str(e)}"

    return jsonify(
        {
            "success": True,
            "status": "confirmed",
            "summary": {
                "template_name": campaign_state["selected_template"],
                "template_display": template.get("name", campaign_state["selected_template"]),
                "leads_count": len(campaign_state["leads_data"]),
                "language": template.get("language", "unknown"),
                "preview_message": preview,
            },
        }
    )


def _run_campaign_worker(campaign_file: Path, template_name: str, dry_run: bool) -> None:
    leads = pd.read_csv(campaign_file)

    def on_progress(_lead, successful, failed):
        with _state_lock:
            campaign_state["progress"] = {
                "processed": successful + failed,
                "successful": successful,
                "failed": failed,
                "total": len(leads),
            }

    try:
        automation = WhatsAppAutomation(
            config=ConfigManager().whatsapp_settings(), progress_callback=on_progress
        )
        result = automation.run_campaign(campaign_file, template_name, dry_run=dry_run)
        with _state_lock:
            campaign_state["status"] = "completed"
            campaign_state["result"] = {
                "total_leads": result.total_leads,
                "successful_sends": result.successful_sends,
                "failed_sends": result.failed_sends,
                "invalid_numbers": result.invalid_numbers,
                "duration_seconds": round(result.duration_seconds, 1),
                "dry_run": dry_run,
            }
    except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
        with _state_lock:
            campaign_state["status"] = "failed"
            campaign_state["error"] = str(exc)


@app.route("/api/campaign/start", methods=["POST"])
def start_campaign():
    if campaign_state["status"] != "confirmed":
        return jsonify({"error": "Campaign not confirmed"}), 400

    dry_run = bool((request.json or {}).get("dry_run", False))
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    campaign_file = UPLOAD_FOLDER / f"campaign_{timestamp}.csv"
    # WhatsAppAutomation.load_leads expects title-case columns.
    pd.DataFrame(
        [
            {
                "Business Name": lead["business_name"],
                "Phone Number": lead["phone_number"],
                "Category": lead.get("category", ""),
            }
            for lead in campaign_state["leads_data"]
        ]
    ).to_csv(campaign_file, index=False)

    with _state_lock:
        campaign_state["status"] = "running"
        campaign_state["campaign_file"] = str(campaign_file)
        campaign_state["progress"] = {"processed": 0, "total": len(campaign_state["leads_data"])}
        campaign_state.pop("result", None)
        campaign_state.pop("error", None)

    threading.Thread(
        target=_run_campaign_worker,
        args=(campaign_file, campaign_state["selected_template"], dry_run),
        daemon=True,
    ).start()

    return jsonify(
        {"success": True, "message": "Campaign started", "vnc_url": "/vnc", "dry_run": dry_run}
    )


@app.route("/api/campaign/progress")
def campaign_progress():
    return jsonify(
        {
            "status": campaign_state["status"],
            "progress": campaign_state.get("progress"),
            "result": campaign_state.get("result"),
            "error": campaign_state.get("error"),
        }
    )


@app.route("/vnc")
def vnc_view():
    return render_template("vnc_view.html")


@app.route("/api/campaign/status")
def get_campaign_status():
    template = None
    if campaign_state["selected_template"]:
        template = template_manager.get_template(campaign_state["selected_template"])

    return jsonify(
        {
            "status": campaign_state["status"],
            "selected_template": campaign_state["selected_template"],
            "template_display": (
                template.get("name", campaign_state["selected_template"]) if template else None
            ),
            "leads_count": len(campaign_state["leads_data"]),
            "has_leads_file": campaign_state["leads_file"] is not None,
        }
    )


@app.route("/api/campaign/reset", methods=["POST"])
def reset_campaign():
    global campaign_state
    campaign_state = {
        "selected_template": None,
        "leads_file": None,
        "leads_data": [],
        "status": "idle",
    }
    return jsonify({"success": True, "message": "Campaign reset"})


@app.route("/static/<path:filename>")
def serve_static(filename):
    return send_from_directory("static", filename)


if __name__ == "__main__":
    # Debug is OFF by default (the Werkzeug debugger is an RCE if the port is
    # exposed). Opt in locally with WA_DEBUG=1.
    debug = os.environ.get("WA_DEBUG", "").lower() in ("1", "true", "yes")
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=debug)  # noqa: S104 - bind all ifaces in container
