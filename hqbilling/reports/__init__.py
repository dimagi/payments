from django.core.urlresolvers import reverse
from corehq.apps.crud.interface import BaseCRUDAdminInterface
from corehq.apps.reports.generic import GenericReportView
from hqbilling.dispatcher import BillingInterfaceDispatcher

class HQBillingReport(GenericReportView):
    section_name = "HQ Billing"
    app_slug = 'hqbilling'
    asynchronous = True
    is_admin_report = True
    exportable = False
    dispatcher = BillingInterfaceDispatcher

    @property
    def default_report_url(self):
        return reverse('billing_default')


class BaseBillingAdminInterface(BaseCRUDAdminInterface, HQBillingReport):
    crud_item_type =  "Rate Item"
    crud_form_update_url = "/hq/billing/form/"

    def validate_document_class(self):
        # todo implement properly
        return True


#class UpdatableItem(GenericTabularReport, HQBillingReport):
#    report_template_path = "hqbilling/reports/updatable_item_report.html"
#    fields = []
#    hide_filters = True
#    exportable = False
#
#    form_class = SMSRateForm
#    item_class = SMSRate
#
#    @property
#    def report_context(self):
#        context = super(UpdatableItem, self).report_context
#        context.update(
#            form=dict(
#                name=self.form_class.__name__,
#                item=self.item_class.__name__
#            ),
#            status_message=self.status_message
#        )
#        return context
#
#    @property
#    def rows(self):
#        all_rates = self.item_class.view(self.item_class.couch_view(),
#            reduce=False,
#            include_docs=True
#        ).all()
#        return [rate.as_row for rate in all_rates]
#
#    @property
#    def status_message(self):
#        return "Currency is in <strong>$ USD</strong>."
