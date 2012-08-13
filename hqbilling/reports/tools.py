from corehq.apps.reports.datatables import DataTablesColumn, DataTablesHeader
from hqbilling.forms import TaxRateUpdateForm
from hqbilling.models import TaxRateByCountry
from hqbilling.reports import UpdatableItem

class TaxRateReport(UpdatableItem):
    slug = "tax_rate"
    name = "Tax Rates by Country"
    form_class = TaxRateUpdateForm
    item_class = TaxRateByCountry

    def get_headers(self):
        headers = DataTablesHeader(
            DataTablesColumn("Country"),
            DataTablesColumn("Tax Rate"),
            DataTablesColumn("Edit")
        )
        return headers

    @property
    def status_message(self):
        return None