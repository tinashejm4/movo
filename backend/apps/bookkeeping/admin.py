from django.contrib import admin
from .models import Account, IntracitySale, ExpenseAccount, Expense, FundsTransfer, Charge, EndOfDayBalance, ExchangeRate, LedgerEntry


admin.site.register([Account, 
                     IntracitySale, 
                     ExpenseAccount, 
                     Expense, 
                     FundsTransfer, 
                     Charge, 
                     EndOfDayBalance, 
                     ExchangeRate,
                     LedgerEntry
                     ])

