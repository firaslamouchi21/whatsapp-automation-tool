import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import pandas as pd
from tqdm import tqdm

from .logger_config import LoggerConfig
from .message_templates import MessageTemplateManager, TemplateError
from .phone_validator import PhoneValidationError, PhoneValidator


@dataclass
class CampaignResult:
    total_leads: int
    successful_sends: int
    failed_sends: int
    invalid_numbers: int
    duration_seconds: float
    records: List[Dict[str, Any]] = field(default_factory=list)


class WhatsAppAutomation:
    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[Callable] = None,
        verbose: bool = False,
    ):
        self.config = self._flatten_config(config or {})
        self.phone_validator = PhoneValidator()
        self.template_manager = MessageTemplateManager()
        self.logger = LoggerConfig.setup_logger(
            "whatsapp_automation",
            Path("logs/whatsapp_automation.log"),
            level=logging.DEBUG if verbose else logging.INFO,
        )
        self.logger.setLevel(logging.DEBUG if verbose else logging.INFO)
        self.progress_callback = progress_callback
        self.rate_limit_delay = int(self.config.get("rate_limit_delay", 20))
        self.wait_time = int(self.config.get("wait_time", 10))
        self.tab_close = bool(self.config.get("tab_close", True))
        self.close_time = int(self.config.get("close_time", 3))
        self.max_retries = max(1, int(self.config.get("max_retries", 3)))
        self.retry_delay = int(self.config.get("retry_delay", 5))

    @staticmethod
    def _flatten_config(config: Dict[str, Any]) -> Dict[str, Any]:
        """Accept either a flat settings dict or a nested one with a ``whatsapp`` key
        (as produced by ``AppConfig.__dict__``), returning the flat form."""
        whatsapp = config.get("whatsapp")
        if whatsapp is None:
            return dict(config)
        if hasattr(whatsapp, "__dict__") and not isinstance(whatsapp, dict):
            return dict(vars(whatsapp))
        return dict(whatsapp)

    def load_leads(self, file_path: Path) -> pd.DataFrame:
        if not file_path.exists():
            raise FileNotFoundError(f"Leads file not found: {file_path}")
        try:
            df = pd.read_csv(file_path)
            required_columns = ["Business Name", "Phone Number"]
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                raise ValueError(f"Missing required columns: {missing_columns}")
            self.logger.info(f"Loaded {len(df)} leads from {file_path}")
            return df
        except Exception as e:
            self.logger.error(f"Error loading leads: {e}")
            raise

    def validate_lead(self, row: pd.Series) -> Optional[Dict[str, Any]]:
        phone_number = row.get("Phone Number")
        business_name = row.get("Business Name", "")
        category = row.get("Category", "")
        if pd.isna(phone_number) or not phone_number:
            return None
        formatted_phone = self.phone_validator.validate_and_format(phone_number)
        if not formatted_phone:
            return None
        return {
            "business_name": str(business_name).strip(),
            "phone_number": formatted_phone,
            "category": str(category).strip(),
            "original_data": row.to_dict(),
        }

    def send_message(self, phone_number: str, message: str, business_name: str) -> bool:
        import pywhatkit

        for attempt in range(1, self.max_retries + 1):
            try:
                time.sleep(3)
                pywhatkit.sendwhatmsg_instantly(
                    phone_no=phone_number,
                    message=message,
                    wait_time=self.wait_time,
                    tab_close=self.tab_close,
                    close_time=self.close_time,
                )
                self.logger.info(f"SUCCESS: Message sent to {business_name} at {phone_number}")
                return True
            except Exception as e:
                if attempt < self.max_retries:
                    self.logger.warning(
                        f"RETRY {attempt}/{self.max_retries - 1}: send to {business_name} "
                        f"failed ({e}); retrying in {self.retry_delay}s"
                    )
                    time.sleep(self.retry_delay)
                else:
                    self.logger.error(
                        f"ERROR: Failed to send to {business_name} after "
                        f"{self.max_retries} attempts: {e}"
                    )
        return False

    def process_campaign(
        self,
        leads_df: pd.DataFrame,
        template_name: str,
        dry_run: bool = False,
        start_index: int = 0,
        end_index: Optional[int] = None,
    ) -> CampaignResult:
        end_index = end_index or len(leads_df)
        leads_to_process = leads_df.iloc[start_index:end_index]
        last_position = len(leads_to_process) - 1
        successful_sends = 0
        failed_sends = 0
        invalid_numbers = 0
        records: List[Dict[str, Any]] = []
        start_time = time.time()
        with tqdm(total=len(leads_to_process), desc="Processing leads", unit="leads") as pbar:
            for position, (_, row) in enumerate(leads_to_process.iterrows()):
                lead = self.validate_lead(row)
                if not lead:
                    invalid_numbers += 1
                    records.append(
                        {
                            "business_name": str(row.get("Business Name", "")),
                            "phone_number": str(row.get("Phone Number", "")),
                            "status": "invalid_number",
                        }
                    )
                    pbar.update(1)
                    continue
                status = "unknown"
                try:
                    message = self.template_manager.render_template(template_name, lead)
                    if dry_run:
                        self.logger.info(
                            f"DRY RUN: Would send to {lead['business_name']} "
                            f"at {lead['phone_number']}"
                        )
                        successful_sends += 1
                        status = "dry_run"
                    elif self.send_message(lead["phone_number"], message, lead["business_name"]):
                        successful_sends += 1
                        status = "sent"
                    else:
                        failed_sends += 1
                        status = "send_failed"
                    if self.progress_callback:
                        self.progress_callback(lead, successful_sends, failed_sends)
                except (TemplateError, PhoneValidationError) as e:
                    self.logger.error(f"Validation error: {e}")
                    failed_sends += 1
                    status = "render_failed"
                records.append(
                    {
                        "business_name": lead["business_name"],
                        "phone_number": lead["phone_number"],
                        "status": status,
                    }
                )
                pbar.update(1)
                if not dry_run and position < last_position:
                    time.sleep(self.rate_limit_delay)
        duration = time.time() - start_time
        result = CampaignResult(
            total_leads=len(leads_to_process),
            successful_sends=successful_sends,
            failed_sends=failed_sends,
            invalid_numbers=invalid_numbers,
            duration_seconds=duration,
            records=records,
        )
        self.logger.info(
            f"Campaign completed: {result.successful_sends} successful, "
            f"{result.failed_sends} failed, {result.invalid_numbers} invalid"
        )
        return result

    def run_campaign(
        self,
        leads_file: Path,
        template_name: str,
        dry_run: bool = False,
        start_index: int = 0,
        end_index: Optional[int] = None,
    ) -> CampaignResult:
        try:
            leads_df = self.load_leads(leads_file)
            if not self.template_manager.validate_template(template_name):
                raise TemplateError(f"Invalid template: {template_name}")
            self.logger.info(f"Starting campaign with template: {template_name}")
            return self.process_campaign(leads_df, template_name, dry_run, start_index, end_index)
        except Exception as e:
            self.logger.error(f"Campaign failed: {e}")
            raise
