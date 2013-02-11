import dateutil
from corehq.apps.crud.views import BaseAdminCRUDFormView
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect, HttpResponse, HttpResponseNotFound, Http404
import json
from django.template.loader import render_to_string
from corehq.apps.domain.decorators import require_superuser
from dimagi.utils.web import render_to_response
from hqbilling.forms import *
from hqbilling.models import *
from hqbilling.tasks import generate_monthly_bills

@require_superuser
def default_billing_report(request):
    from hqbilling.reports.details import MonthlyBillReport
    return HttpResponseRedirect(MonthlyBillReport.get_url())

@require_superuser
def bill_invoice(request, bill_id,
                 itemized=False,
                 template="hqbilling/reports/monthly_bill.html",
                 partial="hqbilling/partials/invoice.html"):
    range_fmt = "%B %d, %Y"
    bill = HQMonthlyBill.get(bill_id)
    from hqbilling.reports.details import MonthlyBillReport
    parent_link = '<a href="%s">%s<a>' % (MonthlyBillReport.get_url(), MonthlyBillReport.name)
    billing_range = "%s to %s" % (bill.billing_period_start.strftime(range_fmt),
                                  bill.billing_period_end.strftime(range_fmt))
    view_title = "%s %s for %s" % (bill.billing_period_start.strftime("%B %Y"),
                                   "Itemized Statement" if itemized else "Invoice",
                                        bill.domain)

    if itemized:
        printable_url = reverse("billing_itemized_print", kwargs=dict(bill_id=bill_id))
    else:
        printable_url = reverse("billing_invoice_print", kwargs=dict(bill_id=bill_id))

    return render_to_response(request, template, dict(
        slug=MonthlyBillReport.slug,
        partial=partial,
        parent_link=parent_link,
        bill=bill,
        view_title=view_title,
        billing_range=billing_range,
        printable_url=printable_url
    ))

@require_superuser
def bill_status_update(request, bill_id, status):
    success=False
    try:
        bill = HQMonthlyBill.get(bill_id)
        if bill:
            bill.paid = (status == 'yes')
            bill.save()
            success=True
    except Exception:
        pass
    return HttpResponse(json.dumps(dict(
        status=status,
        success=success,
        bill_id=bill_id
    )))

class BillingAdminCRUDFormView(BaseAdminCRUDFormView):
    base_loc = "hqbilling.forms"

    def is_form_class_valid(self, form_class):
        # todo
        return True

@require_superuser
def generate_bills(request):
    try:
        start = dateutil.parser.parse(request.GET.get('start'))
        end = dateutil.parser.parse(request.GET.get('end'))
        date_range = [start, end]
    except Exception:
        date_range = None
    generate_monthly_bills(billing_range=date_range, domain_name=request.GET.get('domain'))
    return Http404

#
#def deltestdata(request):
#    all_rates = MachSMSRate.view(MachSMSRate.match_view(),
#        reduce=False,
#        include_docs=True
#    ).all()
#    for rate in all_rates:
#        rate.delete()
#    return HttpResponse("done")
