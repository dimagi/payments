from corehq.apps.reports.datatables import DataTablesColumn, DataTablesHeader
from hqbilling.forms import TaxRateUpdateForm, BillableCurrencyUpdateForm
from hqbilling.models import TaxRateByCountry, BillableCurrency
from hqbilling.reports import BaseBillingAdminInterface


class BillableCurrencyReport(BaseBillingAdminInterface):
    slug = "billable_currency"
    name = "Billable Currencies"

    document_class = BillableCurrency
    form_class = BillableCurrencyUpdateForm

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
    def rows(self):
        rows = []
        for currency in self.currencies:
            rows.append(currency.admin_crud.row)
        return rows

    @property
    def currencies(self):
        return self.document_class.get_all().all()


class TaxRateReport(BaseBillingAdminInterface):
    slug = "tax_rate"
    name = "Tax Rates by Country"

    document_class = TaxRateByCountry
    form_class = TaxRateUpdateForm

    @property
    def headers(self):
        headers = DataTablesHeader(
            DataTablesColumn("Country"),
            DataTablesColumn("Tax Rate"),
            DataTablesColumn("Edit")
        )
        return headers

    @property
    def rows(self):
        rows = []
        for rate in self.tax_rates:
            rows.append(rate.admin_crud.row)
        return rows

    @property
    def tax_rates(self):
        return self.document_class.view("hqbilling/tax_rates",
            include_docs=True,
            reduce=False
        ).all()


