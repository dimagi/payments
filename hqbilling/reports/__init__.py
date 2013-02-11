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
