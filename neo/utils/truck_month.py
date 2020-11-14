from datetime import datetime

from dateutil.relativedelta import relativedelta


def get_next_year(current_time: datetime) -> int:
    return current_time.year + 1


def is_it_before_truck_month_of_the_current_year(current_time: datetime) -> bool:
    if current_time.month < 2:
        return True
    return False


def get_next_truck_month(current_time: datetime) -> relativedelta:
    """
    Returns the next truck month that will grace the world.

    Parameters
    ----------
    current_time: datetime.datetime
        The current time

    Returns
    -------
    dateutil.relativedelta.relativedelta
        The amount of time that must pass before the next coming of truck
    """
    if is_it_before_truck_month_of_the_current_year is True:
        truck_month_year = current_time.year
    else:
        truck_month_year = get_next_year(current_time)
    truck_month = datetime(truck_month_year, 2, 1)
    return relativedelta(truck_month, current_time)
