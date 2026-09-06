import argparse
import sys
from pathlib import Path
from typing import Optional

from config.settings import ConfigManager
from src.message_templates import MessageTemplateManager
from src.whatsapp_automation import CampaignResult, WhatsAppAutomation

# Templates include Arabic / Tunisian text; force UTF-8 output so printing them does
# not crash on consoles with a legacy code page (e.g. Windows cp1252).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter)

    parser.add_argument("--leads", type=Path)

    parser.add_argument("--template", type=str)

    parser.add_argument("--dry-run", action="store_true")

    parser.add_argument("--start", type=int, default=0)

    parser.add_argument("--end", type=int)

    parser.add_argument("--config", type=Path, default=Path("config/config.yaml"))

    parser.add_argument("--list-templates", action="store_true")

    parser.add_argument("--validate-leads", type=Path)

    parser.add_argument("--output", type=Path, default=Path("output"))

    parser.add_argument("--verbose", action="store_true")

    return parser


def list_templates() -> None:
    manager = MessageTemplateManager()
    templates = manager.list_templates()

    print("Available Templates:")
    print("-" * 40)
    for name, description in templates.items():
        print(f"  {name}: {description}")


def validate_leads(leads_file: Path) -> None:
    import pandas as pd

    from src.phone_validator import PhoneValidator

    validator = PhoneValidator()

    try:
        df = pd.read_csv(leads_file)

        if "Phone Number" not in df.columns:
            print("Error: 'Phone Number' column not found in CSV")
            return

        valid_count = 0
        invalid_count = 0
        invalid_numbers = []

        for idx, phone in df["Phone Number"].items():
            if validator.validate_and_format(phone):
                valid_count += 1
            else:
                invalid_count += 1
                invalid_numbers.append((idx + 1, phone))

        print(f"Validation Results for {leads_file}:")
        print(f"  Valid numbers: {valid_count}")
        print(f"  Invalid numbers: {invalid_count}")

        if invalid_numbers:
            print("\nInvalid numbers:")
            for row_num, phone in invalid_numbers[:10]:
                print(f"  Row {row_num}: {phone}")
            if len(invalid_numbers) > 10:
                print(f"  ... and {len(invalid_numbers) - 10} more")

    except Exception as e:
        print(f"Error validating leads: {e}")


def progress_callback(lead, successful, failed):
    print(
        f"\rProgress: {successful + failed} processed, "
        f"{successful} successful, {failed} failed",
        end="",
        flush=True,
    )


def _write_results(result: CampaignResult, output_dir: Path) -> Path:
    import csv
    from datetime import datetime

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"campaign_results_{datetime.now():%Y%m%d_%H%M%S}.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["business_name", "phone_number", "status"])
        writer.writeheader()
        writer.writerows(result.records)
    return path


def run_campaign(args) -> Optional[CampaignResult]:
    config_manager = ConfigManager(args.config)

    automation = WhatsAppAutomation(
        config=config_manager.whatsapp_settings(),
        progress_callback=progress_callback if not args.verbose else None,
        verbose=args.verbose,
    )

    try:
        result = automation.run_campaign(
            leads_file=args.leads,
            template_name=args.template,
            dry_run=args.dry_run,
            start_index=args.start,
            end_index=args.end,
        )

        print("\n\nCampaign Results:")
        print(f"  Total leads: {result.total_leads}")
        print(f"  Successful: {result.successful_sends}")
        print(f"  Failed: {result.failed_sends}")
        print(f"  Invalid numbers: {result.invalid_numbers}")
        print(f"  Duration: {result.duration_seconds:.2f} seconds")

        if args.output and result.records:
            out = _write_results(result, args.output)
            print(f"  Results written to: {out}")

        return result

    except Exception as e:
        print(f"Error running campaign: {e}")
        return None


def main():
    parser = create_parser()
    args = parser.parse_args()

    if args.list_templates:
        list_templates()
        return

    if args.validate_leads:
        validate_leads(args.validate_leads)
        return

    if not args.leads or not args.template:
        parser.print_help()
        print("\nError: --leads and --template are required")
        sys.exit(1)

    if not args.leads.exists():
        print(f"Error: Leads file not found: {args.leads}")
        sys.exit(1)

    result = run_campaign(args)

    if result is None:
        sys.exit(1)


if __name__ == "__main__":
    main()
