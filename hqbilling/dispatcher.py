from corehq.apps.domain.decorators import cls_require_superusers
from corehq.apps.reports.dispatcher import ReportDispatcher
from corehq.apps.reports.views import datespan_default

class BillingInterfaceDispatcher(ReportDispatcher):
    prefix = 'billing_interface'
    map_name = 'BILLING_REPORT_MAP'

    @cls_require_superusers
    @datespan_default
    def dispatch(self, request, *args, **kwargs):
        return super(BillingInterfaceDispatcher, self).dispatch(request, *args, **kwargs)