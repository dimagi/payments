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
        return super(BillingInterfaceDispatcher, self).dispatch(request, *args, **kwargs)
