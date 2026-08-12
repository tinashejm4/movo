def package_initiator(package):
    return package.sender if package.is_sender_initiated else package.receiver


def package_payer(package, invoice):
    if not invoice.is_pay_forward:
        return package_initiator(package)
    return package.receiver if package.is_sender_initiated else package.sender


def package_initiator_user_id(package):
    return package_initiator(package).user_id


def package_payer_user_id(package, invoice):
    return package_payer(package, invoice).user_id
