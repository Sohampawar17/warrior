__version__ = "0.0.1"

import erpnext.controllers.accounts_controller as ac

def bypass_validate_payment_schedule_dates(self):
    return

ac.AccountsController.validate_payment_schedule_dates = bypass_validate_payment_schedule_dates


import warrior.overrides.base_document
