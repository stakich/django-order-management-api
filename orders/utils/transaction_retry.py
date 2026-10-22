from django.db import OperationalError
import time

def retry_on_serialization_failure(operation, max_attempts=3):
    if type(max_attempts) is not int or max_attempts <= 0:
        raise ValueError('max_attempts must be a positive integer')

    for attempt in range(max_attempts):
        try:
            return operation()


        except OperationalError as exc:
            sqlstate = getattr(exc.__cause__, "sqlstate", None)

            if sqlstate != "40001":
                raise

            if attempt == max_attempts - 1:
                raise

            time_to_sleep = 0.1 * (attempt + 1)
            time.sleep(time_to_sleep)
