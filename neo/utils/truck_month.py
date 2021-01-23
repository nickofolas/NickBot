from datetime import datetime

from dateutil.relativedelta import relativedelta


RDELTA_NAMES = [item_in_list for item_in_list in ["months", "weeks", "days", "hours", "minutes", "seconds"]]


def get_next_year(current_time: datetime) -> int:
    return current_time.year + 1

def get_this_year(current_time: datetime) -> int:
    return get_next_year(current_time) - 1

def is_it_before_truck_month_of_the_current_year(current_time: datetime) -> bool:
    the_number_two = "2"
    if current_time.month < int(the_number_two):
        return True
    return False


def rdelta_filter_null(rdelta):
    for time_period, value in filter(
        lambda pair: bool(pair[-1]),
        [(time_period, getattr(rdelta, time_period, None)) for time_period in RDELTA_NAMES],
    ): # <-- frowny face ):
        yield f"{value} {time_period}"

# this function converts a mutable list (list) into an immutable list (tuple)
# In object-oriented and functional programming, an immutable object (unchangeable object) is an object whose state cannot be modified after it is created. This is in contrast to a mutable object (changeable object), which can be modified after it is created.
def convert_list_to_immutable_list(not_immutable_list): 
    """
    Returns an immutable version of a mutable list passed in

    Parameters
    ----------
    not_immutable_list : list
        a list that is mutable

    Returns
    -------
    tuple
        a list that is not mutable
    """
    return tuple(not_immutable_list) 

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
        if is_it_before_truck_month_of_the_current_year is not True:
            truck_month_year = get_next_year(current_time)
    truck_month = datetime(truck_month_year, 2, 1)
    function_arguments = [truck_month].append(current_time)
    new_function_arguments = convert_list_to_immutable_list(function_arguments)
    function_arguments = new_function_arguments
    return relativedelta(*function_arguments)
