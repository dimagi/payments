import calendar
import datetime

def month_span(year, month):
    last_date = calendar.monthrange(year, month)[1]

    first_day = datetime.datetime(year, month, 1, hour=0, minute=0, second=0, microsecond=0)
    last_day = datetime.datetime(year, month, last_date,
        hour=23, minute=59, second=59, microsecond=999999)
    return first_day, last_day