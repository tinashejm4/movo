from django.contrib import admin
from .models import Account, Sale, Receipt, ExpenseType, Expense, FundsTransfer, Charge, EndOfDayBalance


admin.site.register([Account,Sale,Receipt,ExpenseType,Expense,FundsTransfer,Charge,EndOfDayBalance])

