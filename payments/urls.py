from django.conf.urls.defaults import *

urlpatterns = patterns('payments.views',
    url(r'/$', 'default', name='payments_default'),
)