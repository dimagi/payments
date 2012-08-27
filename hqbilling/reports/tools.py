from corehq.apps.reports.datatables import DataTablesColumn, DataTablesHeader
from hqbilling.forms import TaxRateUpdateForm, BillableCurrencyUpdateForm
from hqbilling.models import TaxRateByCountry, BillableCurrency
from hqbilling.reports import UpdatableItem


class BillableCurrencyReport(UpdatableItem):
    slug = "billable_currency"
    name = "Billable Currencies"
    form_class = BillableCurrencyUpdateForm
    item_class = BillableCurrency

    @property
    def headers(self):
        headers = DataTablesHeader(
            DataTablesColumn("Currency Code"),
            DataTablesColumn("Symbol"),
            DataTablesColumn("Last Known Conversion Rate"),
            DataTablesColumn("Conversion Rate Last Updated"),
            DataTablesColumn("Edit")
        )
        return headers

    @property
    def status_message(self):
        return None

class TaxRateReport(UpdatableItem):
    slug = "tax_rate"
    name = "Tax Rates by Country"
    form_class = TaxRateUpdateForm
    item_class = TaxRateByCountry

    @property
    def headers(self):
        headers = DataTablesHeader(
            DataTablesColumn("Country"),
            DataTablesColumn("Tax Rate"),
            DataTablesColumn("Edit")
        )
        return headers

    @property
    def status_message(self):
        return None


