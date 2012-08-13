from corehq.apps.reports.custom import HQReport
from corehq.apps.reports.standard import StandardTabularHQReport
from hqbilling.forms import SMSRateForm
from hqbilling.models import SMSRate

class HQBillingReport(HQReport):
    base_slug = 'billing'
    reporting_section_name = "HQ Billing"
    base_template_name = "hqbilling/billing_reports_base.html"
    asynchronous = True
    is_admin_report = True
    global_root = "/hq/billing/"


class UpdatableItem(HQBillingReport, StandardTabularHQReport):
    template_name = "hqbilling/reports/updatable_item_report.html"
    fields = []
    hide_filters = True
    exportable = False

    form_class = SMSRateForm
    item_class = SMSRate

    def get_default_report_url(self):
        return "#"

    def get_global_params(self):
        super(UpdatableItem, self).get_global_params()

    def get_report_context(self):
        super(UpdatableItem, self).get_report_context()
        self.context.update(dict(
            form = dict(
                name=self.form_class.__name__,
                item=self.item_class.__name__
            ),
            status_message=self.status_message
        ))

    def get_rows(self):
        all_rates = self.item_class.view(self.item_class.couch_view(),
            reduce=False,
            include_docs=True
        ).all()
        return [rate.as_row for rate in all_rates]

    @property
    def status_message(self):
        return "Currency is in <strong>$ USD</strong>."
