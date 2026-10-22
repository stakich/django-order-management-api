
from unittest.mock import Mock, patch

from django.db import OperationalError
from django.test import SimpleTestCase

from orders.utils.transaction_retry import retry_on_serialization_failure


class TransactionRetryTests(SimpleTestCase):

    @staticmethod
    def make_db_error(sqlstate):
        """
        Simulate a Django OperationalError caused
        by a PostgreSQL error with a SQLSTATE.
        """
        original_error = Exception("PostgreSQL error")
        original_error.sqlstate = sqlstate

        django_error = OperationalError("Database operation failed")
        django_error.__cause__ = original_error

        return django_error

    def test_success_first_attempt(self):
        operation = Mock(return_value="success")

        result = retry_on_serialization_failure(operation)

        self.assertEqual(result, "success")
        operation.assert_called_once()

    @patch("orders.utils.transaction_retry.time.sleep")
    def test_retry_then_success(self, mock_sleep):
        serialization_error = self.make_db_error("40001")

        operation = Mock(
            side_effect=[serialization_error, "success"]
        )

        result = retry_on_serialization_failure(
            operation,
            max_attempts=3
        )

        self.assertEqual(result, "success")
        self.assertEqual(operation.call_count, 2)
        mock_sleep.assert_called_once_with(0.1)

    @patch("orders.utils.transaction_retry.time.sleep")
    def test_max_attempts_exceeded(self, mock_sleep):
        serialization_error = self.make_db_error("40001")

        operation = Mock(side_effect=serialization_error)

        with self.assertRaises(OperationalError):
            retry_on_serialization_failure(
                operation,
                max_attempts=3
            )

        self.assertEqual(operation.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)
        self.assertEqual(
            mock_sleep.call_args_list[0].args[0],
            0.1
        )
        self.assertEqual(
            mock_sleep.call_args_list[1].args[0],
            0.2
        )

    @patch("orders.utils.transaction_retry.time.sleep")
    def test_non_serialization_error(self, mock_sleep):
        database_error = self.make_db_error("42P01")
        operation = Mock(side_effect=database_error)

        with self.assertRaises(OperationalError):
            retry_on_serialization_failure(operation)

        operation.assert_called_once()
        mock_sleep.assert_not_called()

    def test_invalid_max_attempts(self):
        invalid_values = [0, -1, 1.5, "3", True, False, None]

        for value in invalid_values:
            with self.subTest(max_attempts=value):
                operation = Mock()

                with self.assertRaises(ValueError):
                    retry_on_serialization_failure(
                        operation,
                        max_attempts=value
                    )

                operation.assert_not_called()

    def test_success_with_falsy_result(self):
        for value in [0, False, None, "", []]:
            with self.subTest(result=value):
                operation = Mock(return_value=value)

                result = retry_on_serialization_failure(
                    operation
                )

                self.assertEqual(result, value)
                operation.assert_called_once()

    def test_max_attempts_one(self):
        serialization_error = self.make_db_error("40001")
        operation = Mock(side_effect=serialization_error)

        with self.assertRaises(OperationalError):
            retry_on_serialization_failure(
                operation,
                max_attempts=1
            )

        operation.assert_called_once()
