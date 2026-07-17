import logging

def normalize_zimbabwean_number(phone_number):
    return phone_number[-9:] if len(phone_number) > 9 else phone_number

def is_valid_zimbabwean_number(phone_number):
    normalized_number = normalize_zimbabwean_number(phone_number)
    logging.info(f"Normalized number: {normalized_number}")  # Debugging line
    return normalized_number.isdigit() and len(normalized_number) == 9 and normalized_number.startswith("7")