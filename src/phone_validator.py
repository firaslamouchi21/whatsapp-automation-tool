import re
from typing import Optional, Union

import phonenumbers
from phonenumbers import NumberParseException, PhoneNumberFormat


class PhoneValidationError(Exception):
    pass


class PhoneValidator:
    def __init__(self, default_region: str = "QA"):
        self.default_region = default_region

    def validate_and_format(self, phone: Union[str, int]) -> Optional[str]:
        if not phone:
            return None
        phone_str = str(phone).strip()

        cleaned = re.sub(r"[^\d+]", "", phone_str)

        if cleaned and not cleaned.startswith("+"):
            cleaned = "+" + cleaned

        if not cleaned:
            return None
        try:
            region = None if cleaned.startswith("+") else self.default_region
            parsed_number = phonenumbers.parse(cleaned, region)
            if not phonenumbers.is_valid_number(parsed_number):
                return None
            return str(phonenumbers.format_number(parsed_number, PhoneNumberFormat.E164))
        except (NumberParseException, ValueError):
            return None

    def is_valid_number(self, phone: Union[str, int]) -> bool:
        return self.validate_and_format(phone) is not None

    def get_country_code(self, phone: Union[str, int]) -> Optional[str]:
        formatted = self.validate_and_format(phone)
        if not formatted:
            return None
        try:
            parsed_number = phonenumbers.parse(formatted)
            return str(parsed_number.country_code)
        except (NumberParseException, ValueError):
            return None
