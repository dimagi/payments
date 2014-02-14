from django.contrib import messages
from corehq.apps.crud.dispatcher import BaseCRUDAdminInterfaceDispatcher
from corehq.apps.domain.decorators import cls_require_superusers
from corehq.apps.reports.views import datespan_default


class BillingInterfaceDispatcher(BaseCRUDAdminInterfaceDispatcher):
    prefix = 'billing_interface'
    map_name = 'BILLING_REPORTS'

    def get_reports(self, domain=None):
        import hqbilling
        attr_name = self.map_name
        return getattr(hqbilling, attr_name, ())

    @cls_require_superusers
    @datespan_default
    def dispatch(self, request, *args, **kwargs):
        response = super(BillingInterfaceDispatcher, self).dispatch(request, *args, **kwargs)
        if kwargs.get('render_as') == 'view' or kwargs.get('render_as') is None:
            messages.info(request, "Notice: This SMS Billing view will be completely phased out in favor of the "
                                   "new accounting framework on April 1st, 2014.")
        return response
