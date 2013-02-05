from corehq.apps.domain.models import Domain
from dimagi.utils.modules import to_function
from django.conf import settings
from django.contrib import messages
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect, HttpResponse, HttpResponseNotFound, Http404
import json
from django.template.loader import render_to_string
from django.shortcuts import render

from corehq.apps.domain.decorators import login_and_domain_required, require_superuser
from corehq.apps.reports.views import datespan_default
from hqbilling.forms import *
from hqbilling.models import *

@require_superuser
def default_billing_report(request):
    from hqbilling.reports.details import MonthlyBillReport
    return HttpResponseRedirect(MonthlyBillReport.get_url())

@require_superuser
def updatable_item_form(request, form, item_type="",
                      item_id="", template="hqbilling/forms/new_rate.html"):
    form_class = eval(form)
    form = form_class()
    success = False
    delete_item  = request.GET.get('delete')
    did_delete = False
    item_result = []

    if item_id and item_type:
        # this is an update of an existing item
        item_type = eval(item_type)
        existing_item = item_type.get(item_id)
        if delete_item:
            existing_item.delete()
            success = True
            did_delete = True
        elif request.method == 'POST':
            form = form_class(request.POST, item_id=existing_item.get_id)
            if form.is_valid():
                item_result = form.update(existing_item)
                success = True
        else:
            form = form_class(existing_item._doc, item_id=existing_item.get_id)
    elif request.method == 'POST':
        form = form_class(request.POST)
        if form.is_valid():
            item_result = form.save()
            form = form_class()
            success = True

    context = dict(form=form)
    return HttpResponse(json.dumps(dict(
            success=success,
            deleted=did_delete,
            form_update=render_to_string(template, context),
            rows=item_result
        )))

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



#
#def deltestdata(request):
#    all_rates = MachSMSRate.view(MachSMSRate.match_view(),
#        reduce=False,
#        include_docs=True
#    ).all()
#    for rate in all_rates:
#        rate.delete()
#    return HttpResponse("done")
