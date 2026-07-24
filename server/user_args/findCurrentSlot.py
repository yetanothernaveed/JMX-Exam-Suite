import datetime
from .enums import WeekDayEnum

def currentSlot():
    now = datetime.datetime.now()
    current_time = now.time()
    day = now.weekday()
    slot = "Special"

    if current_time > datetime.time(8, 0) and current_time < datetime.time(11, 0):
        slot = "8"
    elif current_time > datetime.time(11, 0) and current_time < datetime.time(14, 0):
        slot = "11"
    elif current_time > datetime.time(14, 0) and current_time < datetime.time(17, 0):
        slot = "2"

    return f"{WeekDayEnum(day).name}_{slot}"

if __name__ == "__main__":
    currentSlot()
