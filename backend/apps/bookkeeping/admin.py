from django.contrib import admin
from .models import Account, InterCitySale, IntracitySale, ExpenseAccount, Expense, FundsTransfer, Charge, EndOfDayBalance, ExchangeRate


admin.site.register([Account, InterCitySale, IntracitySale, ExpenseAccount, Expense, FundsTransfer, Charge, EndOfDayBalance, ExchangeRate])

