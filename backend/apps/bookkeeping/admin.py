from django.contrib import admin
from .models import Account, AccountBalance, IntracitySale, ExpenseAccount, Expense, FundsTransfer, Charge, EndOfDayBalance, ExchangeRate


admin.site.register([Account, 
                     IntracitySale, 
                     ExpenseAccount, 
                     Expense, 
                     FundsTransfer, 
                     Charge, 
                     EndOfDayBalance, 
                     ExchangeRate,
                     AccountBalance])

