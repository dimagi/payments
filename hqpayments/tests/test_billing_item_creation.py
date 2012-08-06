from datetime import datetime
import logging
import cookielib
from django.conf import settings
from django.core.handlers.wsgi import WSGIRequest
from django.test import TestCase
from django.test.client import Client
import poster
from corehq.apps.sms.models import SMSLog, MessageLog
from corehq.apps.users.models import CouchUser, WebUser

from corehq.apps.unicel.api import send as unicel_send, InboundParams, DATE_FORMAT, create_from_request as unicel_incoming
from corehq.apps.tropo.api import send as tropo_send
from corehq.apps.sms.mach_api import send as mach_send

# to get this test to actually run, you must specify the following in settings.py
#SMS_TESTING = dict(
#    unicel="+somenumber",
#    tropo="+somenumber",
#    mach="'+somenumber"
#)
from hqpayments.models import *
from hqpayments.tasks import bill_client_for_sms

class BillingItemTests(TestCase):

    def setUp(self):
        self.domain = "biyeun"

        # delete any existing test SMS logs
        all_logs = SMSLog.by_domain_asc(self.domain).all()
        for log in all_logs:
            log.delete()

        # delete any existing billable items
        all_billables = SMSBillableItem.by_domain(self.domain).all()
        for billable in all_billables:
            billable.delete()


        self.usd_rate = CurrencyConversionRate.get_by_code("USD")
        self.usd_rate.conversion = 1.000
        self.usd_rate.source = "static"
        self.usd_rate.last_updated = datetime.datetime.utcnow()
        self.usd_rate.save()

        self.eur_rate = CurrencyConversionRate.get_by_code("EUR")
        self.eur_rate.conversion = 1.800
        self.eur_rate.source = "static"
        self.eur_rate.last_updated = datetime.datetime.utcnow()
        self.eur_rate.save()

        self.unicel_rate = UnicelSMSBillableRate()
        self.unicel_rate.direction = OUTGOING
        self.unicel_rate.base_fee = 0.01
        self.unicel_rate.surcharge = 0.005
        self.unicel_rate.currency_code = self.unicel_rate.currency_code_setting
        self.unicel_rate.last_modified = datetime.datetime.utcnow()
        self.unicel_rate.save()

        self.unicel_incoming_rate = UnicelSMSBillableRate()
        self.unicel_incoming_rate.direction = INCOMING
        self.unicel_incoming_rate.base_fee = 0.05
        self.unicel_incoming_rate.surcharge = 0.0035
        self.unicel_incoming_rate.currency_code = self.unicel_incoming_rate.currency_code_setting
        self.unicel_incoming_rate.last_modified = datetime.datetime.utcnow()
        self.unicel_incoming_rate.save()

        self.tropo_rate = TropoSMSBillableRate()
        self.tropo_rate.direction = OUTGOING
        self.tropo_rate.base_fee = 0.02
        self.tropo_rate.surcharge = 0.006
        self.tropo_rate.currency_code = self.tropo_rate.currency_code_setting
        self.tropo_rate.last_modified = datetime.datetime.utcnow()
        self.tropo_rate.domain = self.domain
        self.tropo_rate.save()

        self.mach_rate = MachSMSBillableRate()
        self.mach_rate.direction = OUTGOING
        self.mach_rate.base_fee = 0.03
        self.mach_rate.surcharge = 0.0075
        self.mach_rate.currency_code = self.mach_rate.currency_code_setting
        self.mach_rate.last_modified = datetime.datetime.utcnow()
        self.mach_rate.country_code = "265"
        self.mach_rate.mcc = "650"
        self.mach_rate.mnc = "10"
        self.mach_rate.network = "CelTel Limited (ZAIN)"
        self.mach_rate.iso = "mw"
        self.mach_rate.country = "Malawi"
        self.mach_rate.save()

        self.mach_number = MachPhoneNumber()
        self.mach_number.phone_number = "+265996536379"
        self.mach_number.country = self.mach_rate.country
        self.mach_number.network = self.mach_rate.network
        self.mach_number.save()

        self.couch_user = WebUser.create(self.domain, "fakebiyeun", "test123")
        self.couch_user.add_phone_number("+5551234567")
        self.couch_user.save()

        self.test_message = "Test of CommCare HQ's SMS Tracking System."
        try:
            self.sms_config = getattr(settings, "SMS_TESTING")
        except AttributeError:
            self.sms_config = None

        try:
            self.tropo_token = getattr(settings, "TROPO_MESSAGING_TOKEN")
        except AttributeError:
            self.tropo_token = None

    def tearDown(self):
        self.usd_rate.delete()
        self.eur_rate.delete()

        self.unicel_rate.delete()
        self.unicel_incoming_rate.delete()
        self.tropo_rate.delete()
        self.mach_rate.delete()

        self.mach_number.delete()
        self.couch_user.delete()

    def testOutgoingUnicelApi(self):
        self.assertEqual(self.unicel_rate.conversion_rate, self.usd_rate.conversion)
        msg = SMSLog(domain = self.domain,
            direction = OUTGOING,
            date = datetime.datetime.utcnow(),
            text = self.test_message)
        msg.save()

        if self.sms_config and self.sms_config.get("unicel"):
            logging.info("LIVE outgoing Unicel SMS Test.")
            msg.phone_number = self.sms_config.get("unicel")
            msg.save()
            data = unicel_send(msg, delay=False)
        else:
            logging.info("Fake outgoing Unicel SMS Test.")
            data = "successful23541253235"
            msg.phone_number = "+555555555"
            msg.save()
            bill_client_for_sms('UnicelSMSBillableItem', msg, **dict(response=data))

        logging.info("Response from UNICEL: %s" % data)

        billable_item = UnicelSMSBillableItem.by_domain_and_direction(self.domain, OUTGOING).first()
        if billable_item:
            self.assertEqual(self.unicel_rate.billable_amount, billable_item.billable_amount)
            self.assertEqual(self.unicel_rate._id, billable_item.rate_id)
            self.assertEqual(msg._id, billable_item.log_id)
            self.assertEqual(self.unicel_rate.conversion_rate, billable_item.conversion_rate)
            self.assertEqual(data, billable_item.unicel_id)

        if not msg.billed:
            raise Exception("There were errors creating a UNICEL billing rate!")


    def testIncomingUnicelApi(self):
        logging.info("Incoming UNICEL Test.")
        self.assertEqual(self.unicel_rate.conversion_rate, self.usd_rate.conversion)
        fake_post = {InboundParams.SENDER: str(self.couch_user.phone_number),
                     InboundParams.MESSAGE: self.test_message,
                     InboundParams.TIMESTAMP: datetime.datetime.now().strftime(DATE_FORMAT),
                     InboundParams.DCS: '8',
                     InboundParams.UDHI: '0'}

        class FakeRequest(object):
            params = {}
            @property
            def REQUEST(self):
                return self.params

        req = FakeRequest()
        req.params = fake_post

        log = unicel_incoming(req, delay=False)
        if log and not log.billed:
            raise Exception("There were errors creating an incoming UNICEL billing rate!")

        billable_item = UnicelSMSBillableItem.by_domain_and_direction(self.domain, INCOMING).first()
        if billable_item:
            self.assertEqual(self.unicel_incoming_rate.billable_amount, billable_item.billable_amount)
            self.assertEqual(self.unicel_incoming_rate._id, billable_item.rate_id)
            self.assertEqual(log._id, billable_item.log_id)
            self.assertEqual(self.unicel_incoming_rate.conversion_rate, billable_item.conversion_rate)
            self.assertEqual("incoming", billable_item.unicel_id)

    def testOutgoingTropoApi(self):
        self.assertEqual(self.tropo_rate.conversion_rate, self.usd_rate.conversion)
        msg = SMSLog(domain = self.domain,
            direction = OUTGOING,
            date = datetime.datetime.utcnow(),
            text = self.test_message)
        msg.save()

        if self.sms_config and self.sms_config.get("tropo") and self.tropo_token:
            logging.info("LIVE outgoing Tropo SMS test.")
            msg.phone_number = self.sms_config.get("tropo")
            msg.save()
            data = tropo_send(msg, delay=False, **dict(messaging_token=self.tropo_token))
        else:
            logging.info("Fake outgoing Tropo SMS test.")
            data = "<session><success>true</success><token>faketoken</token><id>aadfg3Aa321gdc8e628df2\n</id></session>"
            msg.phone_number = "+555555555"
            msg.save()
            bill_client_for_sms('TropoSMSBillableItem', msg, **dict(response=data))

        logging.info("Response from TROPO: %s" % data)
        tropo_id = TropoSMSBillableItem.get_tropo_id(data)
        logging.info("TROPO ID: %s" % tropo_id)

        billable_item = TropoSMSBillableItem.by_domain(self.domain).first()
        if billable_item:
            self.assertEqual(self.tropo_rate.billable_amount, billable_item.billable_amount)
            self.assertEqual(self.tropo_rate._id, billable_item.rate_id)
            self.assertEqual(msg._id, billable_item.log_id)
            self.assertEqual(self.tropo_rate.conversion_rate, billable_item.conversion_rate)
            self.assertEqual(tropo_id, billable_item.tropo_id)

        if not msg.billed:
            raise Exception("There were errors creating a TROPO billing rate!")

    def testOutgoingMachApi(self):
        self.assertEqual(self.mach_rate.conversion_rate, self.eur_rate.conversion)
        msg = SMSLog(domain = self.domain,
            direction = OUTGOING,
            date = datetime.datetime.utcnow(),
            text = self.test_message)
        msg.save()

        if self.sms_config and self.sms_config.get("mach"):
            logging.info("LIVE outgoing Mach SMS test.")
            msg.phone_number = self.sms_config.get("mach")
            msg.save()
            data = mach_send(msg, delay=False)
        else:
            logging.info("Fake outgoing Mach SMS test.")
            msg.phone_number = self.mach_number.phone_number
            msg.save()
            data = "MACH RESPONSE +OK 01 message queued (dest=%s)" % msg.phone_number
            bill_client_for_sms('MachSMSBillableItem', msg, **dict(response=data))

        logging.info("Response from MACH: %s" % data)

        billable_item = MachSMSBillableItem.by_domain(self.domain).first()
        if billable_item:
            self.assertEqual(self.mach_rate.billable_amount, billable_item.billable_amount)
            self.assertEqual(self.mach_rate._id, billable_item.rate_id)
            self.assertEqual(msg._id, billable_item.log_id)
            self.assertEqual(self.mach_rate.conversion_rate, billable_item.conversion_rate)

        if not msg.billed:
            raise Exception("There were errors creating a MACH billing rate!")






