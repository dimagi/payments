from hqbilling.reports import backend_rates, details, tools
from django.utils.translation import ugettext_noop as _

BILLING_REPORTS = (
    (_("Manage SMS Backend Rates"), (
        backend_rates.DimagiRateReport,
        backend_rates.MachRateReport,
        backend_rates.TropoRateReport,
        backend_rates.UnicelRateReport
        )),
    (_("Billing Details"), (
        details.SMSDetailReport,
        details.MonthlyBillReport
        )),
    (_("Billing Tools"), (
        tools.BillableCurrencyReport,
        tools.TaxRateReport
        ))
    )
