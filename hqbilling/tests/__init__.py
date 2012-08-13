try:
    from hqbilling.tests.test_billing_item_creation import *
    from hqbilling.tests.test_monthly_bill import *
except ImportError, e:
    # for some reason the test harness squashes these so log them here for clarity
    # otherwise debugging is a pain
    import logging
    logging.exception(e)
    raise