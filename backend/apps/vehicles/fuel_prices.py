from datetime import datetime
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
import re

import requests
from django.db import transaction
from django.utils import timezone

from .models import FuelPrice, FuelRecord

SOURCE_URL = "https://www.zera.co.zw/"


class _VisibleText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def scrape_zera_prices():
    response = requests.get(SOURCE_URL, timeout=20, headers={"User-Agent": "Movo fuel price tracker"})
    response.raise_for_status()
    parser = _VisibleText()
    parser.feed(response.text)
    text = re.sub(r"\s+", " ", " ".join(parser.parts)).strip()

    date_match = re.search(r"As Of:\s*(\d{2}-\d{2}-\d{4})", text, re.IGNORECASE)
    if not date_match:
        raise ValueError("ZERA page did not contain a valid price date")
    effective_date = datetime.strptime(date_match.group(1), "%d-%m-%Y").date()
    labels = {
        FuelRecord.FuelType.PETROL: r"Petrol\s+Blend\s*\(E20\)",
        FuelRecord.FuelType.DIESEL: r"Diesel\s*\(D50\)",
    }
    prices = {}
    for fuel_type, label in labels.items():
        match = re.search(
            label + r"\s+\$\s*([\d,.]+)\s+USD\s+Per\s+Litre.*?\$\s*([\d,.]+)\s+ZWG\s+Per\s+Litre",
            text,
            re.IGNORECASE,
        )
        if not match:
            raise ValueError(f"ZERA page did not contain complete {fuel_type} prices")
        try:
            usd, zwg = (Decimal(value.replace(",", "")) for value in match.groups())
        except InvalidOperation as error:
            raise ValueError(f"ZERA returned an invalid {fuel_type} price") from error
        if usd <= 0 or zwg <= 0:
            raise ValueError(f"ZERA returned a non-positive {fuel_type} price")
        prices[(fuel_type, FuelPrice.Currency.USD)] = usd
        prices[(fuel_type, FuelPrice.Currency.ZWG)] = zwg
    return effective_date, prices


@transaction.atomic
def refresh_fuel_prices():
    effective_date, prices = scrape_zera_prices()
    created = []
    for (fuel_type, currency), price in prices.items():
        latest = FuelPrice.objects.filter(fuel_type=fuel_type, currency=currency).order_by(
            "-effective_date", "-fetched_at", "-pk"
        ).first()
        if latest is not None and latest.price_per_litre == price:
            continue
        created.append(FuelPrice.objects.create(
            fuel_type=fuel_type,
            currency=currency,
            price_per_litre=price,
            effective_date=effective_date,
            source=SOURCE_URL,
        ))
    return created
