from corehq.apps.domain.decorators import require_superuser, cls_to_view
from corehq.apps.reports.dispatcher import ReportDispatcher
from corehq.apps.reports.views import datespan_default

cls_require_superusers = cls_to_view(additional_decorator=require_superuser)

class BillingInterfaceDispatcher(ReportDispatcher):
    prefix = 'billing_interface'
    map_name = 'BILLING_REPORT_MAP'

    @cls_require_superusers
    @datespan_default
    def dispatch(self, request, *args, **kwargs):
        return super(BillingInterfaceDispatcher, self).dispatch(request, *args, **kwargs)