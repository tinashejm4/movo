def package_initiator(package):
    return package.sender if package.is_sender_initiated else package.receiver


def package_payer(package, invoice):
    return package.receiver if invoice.is_pay_forward else package.sender


def package_initiator_user_id(package):
    return package_initiator(package).user_id


def package_payer_user_id(package, invoice):
    return package_payer(package, invoice).user_id


def package_is_incoming_for_user(package, user_id):
    if user_id == package.receiver.user_id:
        return True
    if user_id == package.sender.user_id:
        return False
    return None


def package_user_can_cancel(package, invoice, user_id):
    if user_id == package_initiator_user_id(package):
        return True
    return invoice is not None and user_id == package_payer_user_id(package, invoice)
