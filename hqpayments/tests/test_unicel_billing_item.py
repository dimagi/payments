from datetime import datetime
from django.test import TestCase
from django.test.client import Client
from corehq.apps.sms.models import SMSLog, MessageLog
from corehq.apps.users.models import CouchUser, WebUser

from corehq.apps.unicel.api import OutboundParams, OUTGOING, DATE_FORMAT, API_ID

class BillingItemTests(TestCase):

    def setUp(self):
        self.domain = "biyeun"
        self.user = "fakebiyeun"
        self.password = "password1"
        self.couch_user = WebUser.create(self.domain, self.user, self.password)
        self.couch_user.add_phone_number(self.phone_number)
        self.couch_user.save()


        self.backend_api = API_ID


