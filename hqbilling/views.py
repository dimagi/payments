from corehq.apps.domain.models import Domain
from dimagi.utils.modules import to_function
from django.conf import settings
from django.contrib import messages
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect, HttpResponse, HttpResponseNotFound, Http404
import json
from django.template.loader import render_to_string
from corehq.apps.domain.decorators import login_and_domain_required, require_superuser
from corehq.apps.reports.views import report_dispatcher, datespan_default
from dimagi.utils.web import render_to_response
from hqbilling.forms import *
from hqbilling.models import *
from hqbilling.reports.details import MonthlyBillReport

@require_superuser
def default_billing_report(request):
    return HttpResponseRedirect(reverse("billing_report_dispatcher", kwargs=dict(report_slug=MonthlyBillReport.slug)))

@require_superuser
@datespan_default
def billing_report_dispatcher(request, report_slug, return_json=False, report_map='BILLING_REPORT_MAP', export=False, async=False, async_filters=False, static_only=False):
    mapping = getattr(settings, report_map, None)
    if not mapping:
        return HttpResponseNotFound("Sorry, no reports have been configured yet.")
    for key, models in mapping.items():
        for model in models:
            klass = to_function(model)
            if klass.slug == report_slug:
                k = klass(None, request)
                if return_json:
                    return k.as_json()
                elif export:
                    return k.as_export()
                elif async:
                    return k.as_async(static_only=static_only)
                elif async_filters:
                    return k.as_async_filters()
                else:
                    return k.as_view()
    raise Http404

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
    parent_link = '<a href="%s">%s<a>' % (reverse("billing_report_dispatcher", kwargs=dict(
        report_slug=MonthlyBillReport.slug
    )), MonthlyBillReport.name)
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



#
#def deltestdata(request):
#    all_rates = MachSMSRate.view(MachSMSRate.match_view(),
#        reduce=False,
#        include_docs=True
#    ).all()
#    for rate in all_rates:
#        rate.delete()
#    return HttpResponse("done")
