from django.conf.urls.defaults import *
from hqbilling.dispatcher import BillingInterfaceDispatcher

urlpatterns = patterns('hqbilling.views',
    url(r'^$', "default_billing_report", name="billing_default"),
    url(BillingInterfaceDispatcher.pattern(), BillingInterfaceDispatcher.as_view(),
        name=BillingInterfaceDispatcher.name()
    ),
#    url(r'^delete/all/', "deltestdata"),

    url(r'^forms/(?P<form>[\w_]+)/(?P<item_type>[\w_]+)/(?P<item_id>[\w_]+)/$', 'updatable_item_form',
        name='billing_update_item_form'),
    url(r'^forms/(?P<form>[\w_]+)/$', 'updatable_item_form', name='billing_new_item_form'),

    url(r'^bill/invoice/(?P<bill_id>[\w-]+)/$', 'bill_invoice',
        name='billing_invoice'),
    url(r'^bill/print/invoice/(?P<bill_id>[\w-]+)/$', 'bill_invoice',
        name='billing_invoice_print',
        kwargs=dict(template='hqbilling/reports/monthly_bill_print.html')),

    url(r'^bill/itemized/(?P<bill_id>[\w-]+)/$', 'bill_invoice',
        name='billing_itemized',
        kwargs=dict(partial='hqbilling/partials/itemized.html', itemized=True)),
    url(r'^bill/print/itemized/(?P<bill_id>[\w-]+)/$', 'bill_invoice',
        name='billing_itemized_print',
        kwargs=dict(partial='hqbilling/partials/itemized.html',
            template='hqbilling/reports/monthly_bill_print.html', itemized=True)),

    url(r'^bill/status/(?P<bill_id>[\w-]+)/(?P<status>[(yes)|(no)]+)/$', 'bill_status_update',
        name='billing_update_bill'),

)