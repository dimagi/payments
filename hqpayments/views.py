from django.contrib import messages
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect, HttpResponse
import json
from django.template.loader import render_to_string
from corehq.apps.domain.decorators import login_and_domain_required, require_superuser
from dimagi.utils.web import render_to_response
from hqpayments import forms
from hqpayments.models import MACH_DEFAULT_BASE, MachSMSBillableRate

def get_base_backend_context(request):
    return dict(
        layout_flush_content=True
    )

@require_superuser
def admin_overview(request, template="hqpayments/admin_payments_base.html"):
    return render_to_response(request, template, dict())

@require_superuser
def mach_backend(request, template="hqpayments/admin/backends/mach.html"):
    context = get_base_backend_context(request)
    mach_form = forms.MachExcelFileUploadForm()
    rate_form = forms.MachBillableItemForm()
    all_rates = MachSMSBillableRate.view('hqpayments/mach_rates',
        reduce=False,
        include_docs=True
        ).all()
#    for rate in rates:
#        rate.delete()
    if request.method == 'POST' and request.FILES:
        mach_form = forms.MachExcelFileUploadForm(request.POST, request.FILES)
        if mach_form.is_valid():
            mach_form.save()
    elif request.method == 'POST':
        rate_form = forms.MachBillableItemForm(data=request.POST)
        if rate_form.is_valid():
            rate_form.save()
            rate_form = forms.MachBillableItemForm()
            success=True
        else:
            success=False
        template = "hqpayments/admin/partials/rate_item_form.html"
        context['rate_form'] = rate_form
        return HttpResponse(json.dumps(dict(
            success=success,
            form_update=render_to_string(template, context)
        )))


    context['rate_form'] = rate_form
    context['rate_partial'] = 'hqpayments/admin/partials/mach_rate_form.html'
    context['mach_upload_form'] = mach_form
    context['base_rate'] = MACH_DEFAULT_BASE
    context['rates'] = all_rates

    return render_to_response(request, template, context)