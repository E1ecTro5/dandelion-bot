from aiogram.filters.callback_data import CallbackData

class ConfirmAction(CallbackData, prefix="confirm_dl"):
    action: str # action type
    download_id: str