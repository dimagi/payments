from django.test import TestCase
from corehq.apps.domain.models import Domain
from corehq.apps.sms.mixin import VerifiedNumber
from corehq.apps.sms.models import SMSLog
from corehq.apps.sms.util import clean_phone_number, strip_plus
from corehq.apps.users.models import WebUser

from corehq.apps.unicel.api import (UnicelBackend, InboundParams, DATE_FORMAT,
                                    create_from_request as unicel_incoming)
from corehq.apps.tropo.api import TropoBackend
from corehq.apps.mach.api import MachBackend
from corehq.apps.sms.api import incoming as create_incoming_msg

from hqbilling.models import *
from hqbilling.tasks import bill_client_for_sms

# to get this test to actually run, you must specify the following in settings.py
#SMS_TESTING = dict(
#    unicel="+somenumber",
#    tropo="+somenumber",
#    mach="'+somenumber"
#)
#
# Also needed for the live tests are the following localsettings config items hooked
# up to actual accounts:
#
#UNICEL_CONFIG = {
#   "username" : "...",
#   "password" : "...",
#   "sender" : "...",
#}
#
#TROPO_MESSAGING_TOKEN = "..."
#
#MACH_CONFIG = {
#   "username" : "...",
#   "password" : "...",
#}

class BillingItemTests(TestCase):

    def setUp(self):
        self.domain = "biyeun"

        self.domain_obj = Domain()
        self.domain_obj.name = self.domain
        self.domain_obj.commtrack_enabled = True
        self.domain_obj.save()

        # delete any existing test SMS logs
        all_logs = SMSLog.by_domain_asc(self.domain).all()
        for log in all_logs:
            log.delete()

        # delete any existing billable items
        all_billables = SMSBillable.by_domain(self.domain)
        for billable in all_billables:
            billable.delete()

        self.usd_rate = BillableCurrency.get_existing_or_new_by_code("USD")
        self.usd_rate.conversion = 1.000
        self.usd_rate.source = "static"
        self.usd_rate.last_updated = datetime.datetime.utcnow()
        self.usd_rate.save()

        self.eur_rate = BillableCurrency.get_existing_or_new_by_code("EUR")
        self.eur_rate.conversion = 1.800
        self.eur_rate.source = "static"
        self.eur_rate.last_updated = datetime.datetime.utcnow()
        self.eur_rate.save()

        self.dimagi_surcharge = DimagiDomainSMSRate()
        self.dimagi_surcharge.domain = self.domain
        self.dimagi_surcharge.direction = OUTGOING
        self.dimagi_surcharge.base_fee = 0.002
        self.dimagi_surcharge.currency_code = self.dimagi_surcharge._admin_crud_class.currency_code
        self.dimagi_surcharge.last_modified = datetime.datetime.utcnow()
        self.dimagi_surcharge.save()

        self.dimagi_surcharge_I = DimagiDomainSMSRate()
        self.dimagi_surcharge_I.domain = self.domain
        self.dimagi_surcharge_I.direction = INCOMING
        self.dimagi_surcharge_I.base_fee = 0.001
        self.dimagi_surcharge_I.currency_code = self.dimagi_surcharge._admin_crud_class.currency_code
        self.dimagi_surcharge_I.last_modified = datetime.datetime.utcnow()
        self.dimagi_surcharge_I.save()

        self.unicel_rate = UnicelSMSRate()
        self.unicel_rate.direction = OUTGOING
        self.unicel_rate.base_fee = 0.01
        self.unicel_rate.currency_code = self.unicel_rate._admin_crud_class.currency_code
        self.unicel_rate.last_modified = datetime.datetime.utcnow()
        self.unicel_rate.save()

        self.unicel_incoming_rate = UnicelSMSRate()
        self.unicel_incoming_rate.direction = INCOMING
        self.unicel_incoming_rate.base_fee = 0.05
        self.unicel_incoming_rate.currency_code = self.unicel_incoming_rate._admin_crud_class.currency_code
        self.unicel_incoming_rate.last_modified = datetime.datetime.utcnow()
        self.unicel_incoming_rate.save()

        self.tropo_rate_any = TropoSMSRate()
        self.tropo_rate_any.direction = OUTGOING
        self.tropo_rate_any.base_fee = 0.02
        self.tropo_rate_any.country_code = ""
        self.tropo_rate_any.currency_code = self.tropo_rate_any._admin_crud_class.currency_code
        self.tropo_rate_any.last_modified = datetime.datetime.utcnow()
        self.tropo_rate_any.save()

        self.tropo_rate_us = TropoSMSRate()
        self.tropo_rate_us.direction = OUTGOING
        self.tropo_rate_us.base_fee = 0.01
        self.tropo_rate_us.country_code = "1"
        self.tropo_rate_us.currency_code = self.tropo_rate_us._admin_crud_class.currency_code
        self.tropo_rate_us.last_modified = datetime.datetime.utcnow()
        self.tropo_rate_us.save()

        self.tropo_rate_incoming = TropoSMSRate()
        self.tropo_rate_incoming.direction = INCOMING
        self.tropo_rate_incoming.base_fee = 0.0123
        self.tropo_rate_incoming.country_code = ""
        self.tropo_rate_incoming.currency_code = self.tropo_rate_incoming._admin_crud_class.currency_code
        self.tropo_rate_incoming.last_modified = datetime.datetime.utcnow()
        self.tropo_rate_incoming.save()


        # self.mach_rate = MachSMSRate()
        # self.mach_rate.direction = OUTGOING
        # self.mach_rate.base_fee = 0.005
        # self.mach_rate.network_surcharge = 0.0075
        # self.mach_rate.currency_code = self.mach_rate._admin_crud_class.currency_code
        # self.mach_rate.last_modified = datetime.datetime.utcnow()
        # self.mach_rate.country_code = "49"
        # self.mach_rate.mcc = "262"
        # self.mach_rate.mnc = "07"
        # self.mach_rate.network = "O2"
        # self.mach_rate.iso = "de"
        # self.mach_rate.country = "Germany"
        # self.mach_rate.save()
        #
        #
        # self.mach_number = MachPhoneNumber()
        # self.mach_number.phone_number = "+4917685675599"
        # self.mach_number.country = self.mach_rate.country
        # self.mach_number.network = self.mach_rate.network
        # self.mach_number.save()


        # FOR INCOMING UNICEL
        # Couch User with Verified Phone Number
        self.unicel_couch_user = WebUser.create(self.domain, "unicel_biyeun", "test123")
        self.unicel_couch_user.add_phone_number("+919971855708")
        self.unicel_couch_user.save()
        # Verified Number for Incoming Unicel Message
        self.vn_unicel = VerifiedNumber()
        self.vn_unicel.owner_id = self.unicel_couch_user.get_id
        self.vn_unicel.owner_doc_type = self.unicel_couch_user.__class__.__name__
        self.vn_unicel.domain = self.domain
        self.vn_unicel.backend_id = None # This is not needed unless you use corehq.apps.sms.api.send_sms_to_verified_number
        self.vn_unicel.phone_number = strip_plus(clean_phone_number(self.unicel_couch_user.phone_number))
        self.vn_unicel.verified = True
        self.vn_unicel.save()


        # FOR INCOMING TROPO
        # Couch User with Verified Phone Number
        self.tropo_couch_user = WebUser.create(self.domain, "tropo_biyeun", "test123")
        self.tropo_couch_user.add_phone_number("+4917685675599")
        self.tropo_couch_user.save()
        # Verified Phone Number for Incoming Tropo Message
        self.vn_tropo = VerifiedNumber()
        self.vn_tropo.owner_id = self.tropo_couch_user.get_id
        self.vn_tropo.owner_doc_type = self.tropo_couch_user.__class__.__name__
        self.vn_tropo.domain = self.domain
        self.vn_tropo.backend_id = None # This is not needed unless you use corehq.apps.sms.api.send_sms_to_verified_number
        self.vn_tropo.phone_number = strip_plus(clean_phone_number(self.tropo_couch_user.phone_number))
        self.vn_tropo.verified = True
        self.vn_tropo.save()


        self.test_message = "Test of CommCare HQ's SMS Tracking System."
        try:
            self.sms_config = getattr(settings, "SMS_TESTING")
        except AttributeError:
            self.sms_config = None

        try:
            self.tropo_token = getattr(settings, "TROPO_MESSAGING_TOKEN")
            self.tropo_backend = TropoBackend(messaging_token=self.tropo_token)
        except AttributeError:
            self.tropo_token = None
            self.tropo_backend = None

        try:
            unicel_config = getattr(settings, "UNICEL_CONFIG")
            self.unicel_backend = UnicelBackend(
                username=unicel_config["username"],
                password=unicel_config["password"],
                sender=unicel_config["sender"],
            )
        except (AttributeError, KeyError):
            self.unicel_backend = None

        # try:
        #     mach_config = getattr(settings, "MACH_CONFIG")
        #     self.mach_backend = MachBackend(
        #         account_id=mach_config["username"],
        #         password=mach_config["password"],
        #         sender_id="TEST",
        #     )
        # except (AttributeError, KeyError):
        #     self.mach_backend = None

    def tearDown(self):
        self.usd_rate.delete()
        self.eur_rate.delete()

        self.dimagi_surcharge.delete()
        self.dimagi_surcharge_I.delete()

        self.unicel_rate.delete()
        self.unicel_incoming_rate.delete()

        self.tropo_rate_any.delete()
        self.tropo_rate_us.delete()
        self.tropo_rate_incoming.delete()

        # self.mach_rate.delete()
        #
        # self.mach_number.delete()

        self.unicel_couch_user.delete()
        self.vn_unicel.delete()

        self.tropo_couch_user.delete()
        self.vn_tropo.delete()

        self.domain_obj.delete()

    def testOutgoingUnicelApi(self):
        self.assertEqual(self.unicel_rate.conversion_rate, self.usd_rate.conversion)
        msg = SMSLog(domain = self.domain,
            direction = OUTGOING,
            date = datetime.datetime.utcnow(),
            text = self.test_message)
        msg.save()

        if self.sms_config and self.sms_config.get("unicel") and self.unicel_backend:
            logging.info("\n\n[Billing - LIVE] UNICEL: Outgoing SMS Test.")
            msg.phone_number = self.sms_config.get("unicel")
            msg.save()
            data = self.unicel_backend.send(msg, delay=False)
        else:
            logging.info("\n\n[Billing] UNICEL: Outgoing SMS Test")
            data = "successful23541253235"
            msg.phone_number = "+555555555"
            msg.save()
            bill_client_for_sms(UnicelSMSBillable, msg.get_id, **dict(response=data))

        logging.info("Response from UNICEL: %s" % data)

        billable_items = UnicelSMSBillable.by_domain_and_direction(self.domain, OUTGOING)
        if billable_items:
            billable_item = billable_items[0]
            self.assertEqual(self.unicel_rate.base_fee * self.unicel_rate.conversion_rate,
                       billable_item.billable_amount)
            self.assertEqual(self.unicel_rate._id, billable_item.rate_id)
            self.assertEqual(msg._id, billable_item.log_id)
            self.assertEqual(self.unicel_rate.conversion_rate, billable_item.conversion_rate)
            self.assertEqual(self.dimagi_surcharge.base_fee, billable_item.dimagi_surcharge)
            self.assertEqual(data, billable_item.unicel_id)
            if billable_item.has_error:
                raise Exception("There were recorded errors creating an outgoing UNICEL billing rate: %s" %
                                billable_item.error_message)
        else:
            raise Exception("There were unknown errors creating an outgoing UNICEL billing rate!")


    def testIncomingUnicelApi(self):
        logging.info("\n\n[Billing] UNICEL: Incoming SMS Test")
        self.assertEqual(self.unicel_rate.conversion_rate, self.usd_rate.conversion)
        fake_post = {InboundParams.SENDER: str(self.unicel_couch_user.phone_number),
                     InboundParams.MESSAGE: self.test_message,
                     InboundParams.TIMESTAMP: datetime.datetime.now().strftime(DATE_FORMAT),
                     InboundParams.DCS: '8',
                     InboundParams.UDHI: '0'}

        class FakeRequest(object):
            # HACK
            params = {}
            @property
            def REQUEST(self):
                return self.params

        req = FakeRequest()
        req.params = fake_post

        log = unicel_incoming(req, delay=False)

        billable_items = UnicelSMSBillable.by_domain_and_direction(self.domain, INCOMING)
        if billable_items:
            billable_item = billable_items[0]
            self.assertEqual(self.unicel_incoming_rate.base_fee,
                                   billable_item.billable_amount)
            self.assertEqual(self.unicel_incoming_rate._id, billable_item.rate_id)
            self.assertEqual(log._id, billable_item.log_id)
            self.assertEqual(self.unicel_incoming_rate.conversion_rate, billable_item.conversion_rate)
            self.assertEqual(self.dimagi_surcharge_I.base_fee, billable_item.dimagi_surcharge)
            self.assertEqual(INCOMING_MSG_ID, billable_item.unicel_id)
            if billable_item.has_error:
                raise Exception("There were recorded errors creating an incoming UNICEL billing rate: %s" %
                                billable_item.error_message)
        else:
            raise Exception("There were unknown errors creating an incoming UNICEL billing rate!")

    def testOutgoingUSTropoApi(self):
        self.assertEqual(self.tropo_rate_us.conversion_rate, self.usd_rate.conversion)
        msg = SMSLog(domain = self.domain,
            direction = OUTGOING,
            date = datetime.datetime.utcnow(),
            text = self.test_message)
        msg.save()

        if self.sms_config and self.sms_config.get("tropo_us") and self.tropo_backend:
            logging.info("\n\n[Billing - LIVE] Tropo: Outgoing US SMS Test")
            msg.phone_number = self.sms_config.get("tropo_us")
            msg.save()
            data = self.tropo_backend.send(msg, delay=False)
        else:
            logging.info("\n\n[Billing] Tropo: Outgoing US SMS Test")
            data = "<session><success>true</success><token>faketoken</token><id>aadfg3Aa321gdc8e628df2\n</id></session>"
            msg.phone_number = "+16175005454"
            msg.save()
            bill_client_for_sms(TropoSMSBillable, msg.get_id, **dict(response=data))

        logging.info("Response from TROPO: %s" % data)
        tropo_id = TropoSMSBillable.get_tropo_id(data)
        logging.info("TROPO ID: %s" % tropo_id)

        billable_items = TropoSMSBillable.by_domain(self.domain)
        if billable_items:
            billable_item = billable_items[0]
            self.assertEqual(self.tropo_rate_us.base_fee,
                billable_item.billable_amount)
            self.assertEqual(self.tropo_rate_us._id, billable_item.rate_id)
            self.assertEqual(msg._id, billable_item.log_id)
            self.assertEqual(self.tropo_rate_us.conversion_rate, billable_item.conversion_rate)
            self.assertEqual(self.dimagi_surcharge.base_fee, billable_item.dimagi_surcharge)
            self.assertEqual(tropo_id, billable_item.tropo_id)
            billable_item.delete()
            if billable_item.has_error:
                raise Exception("There were recorded errors creating an outgoing US Tropo billing rate: %s" %
                                billable_item.error_message)
        else:
            raise Exception("There were unknown errors creating an outgoing US Tropo billing rate!")

    def testOutgoingInternationalTropoApi(self):
        self.assertEqual(self.tropo_rate_any.conversion_rate, self.usd_rate.conversion)
        msg = SMSLog(domain = self.domain,
            direction = OUTGOING,
            date = datetime.datetime.utcnow(),
            text = self.test_message)
        msg.save()

        if self.sms_config and self.sms_config.get("tropo_int") and self.tropo_backend:
            logging.info("\n\n[Billing - LIVE] Tropo:  Outgoing International SMS Test")
            msg.phone_number = self.sms_config.get("tropo_int")
            msg.save()
            data = self.tropo_backend.send(msg, delay=False)
        else:
            logging.info("\n\n[Billing] Tropo: Outgoing International SMS Test")
            data = "<session><success>true</success><token>faketoken</token><id>aadfg3Aa321gdc8e628df2\n</id></session>"
            msg.phone_number = "+4915253271951"
            msg.save()
            bill_client_for_sms(TropoSMSBillable, msg.get_id, **dict(response=data))

        logging.info("[Billing] Response from TROPO: %s" % data)
        tropo_id = TropoSMSBillable.get_tropo_id(data)
        logging.info("[Billing] TROPO ID: %s" % tropo_id)

        billable_items = TropoSMSBillable.by_domain(self.domain)
        if billable_items:
            billable_item = billable_items[0]
            self.assertEqual(self.tropo_rate_any.base_fee,
                billable_item.billable_amount)
            self.assertEqual(self.tropo_rate_any._id, billable_item.rate_id)
            self.assertEqual(msg._id, billable_item.log_id)
            self.assertEqual(self.tropo_rate_any.conversion_rate, billable_item.conversion_rate)
            self.assertEqual(self.dimagi_surcharge.base_fee, billable_item.dimagi_surcharge)
            self.assertEqual(tropo_id, billable_item.tropo_id)
            billable_item.delete()
            if billable_item.has_error:
                raise Exception("There were recorded errors creating an outgoing International Tropo billing rate: %s" %
                                billable_item.error_message)
        else:
            raise Exception("There were unknown errors creating an outgoing International Tropo billing rate!")

    def testIncomingTropoApi(self):
        logging.info("\n\n[Billing] Tropo: Incoming SMS Test")
        self.assertEqual(self.tropo_rate_incoming.conversion_rate, self.usd_rate.conversion)
        # fake_post = {InboundParams.SENDER: str(self.tropo_couch_user.phone_number),
        #              InboundParams.MESSAGE: self.test_message,
        #              InboundParams.TIMESTAMP: datetime.datetime.now().strftime(DATE_FORMAT),
        #              InboundParams.DCS: '8',
        #              InboundParams.UDHI: '0'}
        #
        # class FakeRequest(object):
        #     # HACK
        #     params = {}
        #     @property
        #     def REQUEST(self):
        #         return self.params
        #
        # req = FakeRequest()
        # req.params = fake_post

        log = create_incoming_msg(str(self.tropo_couch_user.phone_number), self.test_message, TropoBackend.get_api_id(), delay=False)

        billable_items = TropoSMSBillable.by_domain_and_direction(self.domain, INCOMING)

        if billable_items:
            billable_item = billable_items[0]
            self.assertEqual(self.tropo_rate_incoming.base_fee, billable_item.billable_amount)
            self.assertEqual(self.tropo_rate_incoming._id, billable_item.rate_id)
            self.assertEqual(log._id, billable_item.log_id)
            self.assertEqual(self.tropo_rate_incoming.conversion_rate, billable_item.conversion_rate)
            self.assertEqual(self.dimagi_surcharge_I.base_fee, billable_item.dimagi_surcharge)
            self.assertEqual(INCOMING_MSG_ID, billable_item.tropo_id)
            if billable_item.has_error:
                raise Exception("There were recorded errors creating an incoming Tropo billing rate: %s" %
                                billable_item.error_message)
        else:
            raise Exception("There were unknown errors creating an incoming Tropo billing rate!")


    # def testOutgoingMachApi(self):
    #     self.assertEqual(self.mach_rate.conversion_rate, self.eur_rate.conversion)
    #     msg = SMSLog(
    #         domain = self.domain,
    #         direction = OUTGOING,
    #         date = datetime.datetime.utcnow(),
    #         text = self.test_message)
    #     msg.save()
    #
    #     if self.sms_config and self.sms_config.get("mach") and self.mach_backend:
    #         logging.info("\n\n[Billing - LIVE] MACH: Outgoing SMS test")
    #         msg.phone_number = self.sms_config.get("mach")
    #         msg.save()
    #         data = self.mach_backend.send(msg, delay=False)
    #     else:
    #         logging.info("\n\n[Billing] MACH: Outgoing SMS test")
    #         msg.phone_number = self.mach_number.phone_number
    #         msg.save()
    #         data = "MACH RESPONSE +OK 01 message queued (dest=%s)" % msg.phone_number
    #         bill_client_for_sms(MachSMSBillable, msg.get_id, **dict(response=data,
    #             _test_scrape=[['43535235Test', 'test', 'TEST', self.mach_number.phone_number,
    #                            '09.08. 15:44:12', '09.08. 15:44:20', 'Germany O2 ',
    #                            'delivered']]))
    #
    #     logging.info("Response from MACH: %s" % data)
    #
    #     billable_items = MachSMSBillable.by_domain(self.domain)
    #     if billable_items:
    #         billable_item = billable_items[0]
    #         self.assertEqual(self.mach_rate.base_fee + self.mach_rate.network_surcharge,
    #             billable_item.billable_amount)
    #         self.assertEqual(self.mach_rate._id, billable_item.rate_id)
    #         self.assertEqual(msg._id, billable_item.log_id)
    #         self.assertEqual(self.mach_rate.conversion_rate, billable_item.conversion_rate)
    #         self.assertEqual(self.dimagi_surcharge.base_fee, billable_item.dimagi_surcharge)
    #         billable_item.delete()
    #         if billable_item.has_error:
    #             raise Exception("There were recorded errors creating an outgoing MACH billing rate: %s" %
    #                             billable_item.error_message)
    #     else:
    #         raise Exception("There were unknown errors creating an outgoing MACH billing rate!")






