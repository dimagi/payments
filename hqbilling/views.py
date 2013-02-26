import dateutil
from django.template import RequestContext
from tastypie.http import HttpBadRequest
from corehq.apps.crud.views import BaseAdminCRUDFormView
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect, HttpResponse, HttpResponseNotFound, Http404
import json
from django.template.loader import render_to_string
from django.shortcuts import render

from corehq.apps.domain.decorators import require_superuser
from corehq.apps.domain.models import Domain

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

    return render(request, template, dict(
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
    status = "Last Month"
    domain = request.GET.get('domain')
    domain_status = domain or "all domains"
    try:
        start = dateutil.parser.parse(request.GET.get('start'))
        end = dateutil.parser.parse(request.GET.get('end'))
        end = end.replace(minute=59, hour=23, second=59, microsecond=999999)
        date_range = [start, end]
        status = "%s through %s" % (start, end)
    except Exception as e:
        date_range = None
    generate_monthly_bills(billing_range=date_range, domain_name=domain)
    return HttpResponse("Bills generated for %s on %s." % (status, domain_status))


@require_superuser
def update_client_info(request, domain):
    try:
        domain = Domain.get_by_name(domain)
    except Exception as e:
        return HttpBadRequest("Could not fetch domain due to %s" % e)

    success = False
    if request.method == "POST":
        client_form = UpdateBillingStatusForm(request.POST)
        if client_form.is_valid():
            success = client_form.save(domain)
    else:
        client_form = UpdateBillingStatusForm(initial={
            'is_sms_billable': domain.is_sms_billable,
            'billable_client': domain.billable_client
        })

    form_response = render_to_string("hqbilling/forms/client_info.html", {
        "form": client_form
    }, context_instance=RequestContext(request))

    button_response = render_to_string("hqbilling/partials/update_client_button.html", {
        "domain": domain.name,
        "client_name": domain.billable_client,
        "is_active": domain.is_sms_billable,
    })

    return HttpResponse(json.dumps({
        'form': form_response,
        'success': success,
        'domain': domain.name,
        'button': button_response,
    }))

#
#def deltestdata(request):
#    all_rates = MachSMSRate.view(MachSMSRate.match_view(),
#        reduce=False,
#        include_docs=True
#    ).all()
#    for rate in all_rates:
#        rate.delete()
#    return HttpResponse("done")
