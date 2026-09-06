__version__ = "1.0.0"
__author__ = "Firas"
__email__ = "contact@example.com"

from .message_templates import MessageTemplateManager
from .phone_validator import PhoneValidator
from .whatsapp_automation import WhatsAppAutomation

__all__ = ["WhatsAppAutomation", "PhoneValidator", "MessageTemplateManager"]
