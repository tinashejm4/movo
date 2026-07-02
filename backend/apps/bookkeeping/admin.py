from django.contrib import admin
from .models import Account, InterCitySale, IntracitySale, ExpenseType, Expense, FundsTransfer, Charge, EndOfDayBalance


admin.site.register([Account,InterCitySale,IntracitySale,ExpenseType,Expense,FundsTransfer,Charge,EndOfDayBalance])

