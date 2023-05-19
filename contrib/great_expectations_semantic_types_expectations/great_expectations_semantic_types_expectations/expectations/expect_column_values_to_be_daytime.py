"""
This is a template for creating custom ColumnMapExpectations.
For detailed instructions on how to use it, please see:
    https://docs.greatexpectations.io/docs/guides/expectations/creating_custom_expectations/how_to_create_custom_column_map_expectations
"""
from typing import Optional

import ephem
from dateutil.parser import parse

from great_expectations.core.expectation_configuration import ExpectationConfiguration
from great_expectations.execution_engine import PandasExecutionEngine
from great_expectations.expectations.expectation import ColumnMapExpectation
from great_expectations.expectations.metrics import (
    ColumnMapMetricProvider,
    column_condition_partial,
)


def is_daytime(ts, lat, lon) -> bool:
    d = parse(ts) if isinstance(ts, str) else ts
    try:
        obs = ephem.Observer()
        obs.lat = float(lat)
        obs.lon = float(lon)
        obs.date = d.date()
    except Exception:
        return False

    rising_ts = obs.next_rising(ephem.Sun()).datetime()
    next_setting_ts = obs.next_setting(ephem.Sun()).datetime()

    return d >= rising_ts and d < next_setting_ts


# This class defines a Metric to support your Expectation.
# For most ColumnMapExpectations, the main business logic for calculation will live in this class.
class ColumnValuesToBeDaytime(ColumnMapMetricProvider):

    # This is the id string that will be used to reference your metric.
    condition_metric_name = "column_values.daytime"
    condition_value_keys = (
        "lat",
        "lon",
    )

    # This method implements the core logic for the PandasExecutionEngine
    @column_condition_partial(engine=PandasExecutionEngine)
    def _pandas(cls, column, lat, lon, **kwargs):
        return column.apply(lambda x: is_daytime(x, lat, lon))

    # This method defines the business logic for evaluating your metric when using a SqlAlchemyExecutionEngine
    # @column_condition_partial(engine=SqlAlchemyExecutionEngine)
    # def _sqlalchemy(cls, column, _dialect, **kwargs):
    #     raise NotImplementedError

    # This method defines the business logic for evaluating your metric when using a SparkDFExecutionEngine
    # @column_condition_partial(engine=SparkDFExecutionEngine)
    # def _spark(cls, column, **kwargs):
    #     raise NotImplementedError


# This class defines the Expectation itself
class ExpectColumnValuesToBeDaytime(ColumnMapExpectation):
    """Expect the provided timestamp is daytime at the given GPS coordinate (latitude, longitude)."""

    # These examples will be shown in the public gallery.
    # They will also be executed as unit tests for your Expectation.
    examples = [
        {
            "data": {
                "all_daytime": [
                    "2022-04-01 12:00:00",
                    "2022-04-02 14:31:14",
                    "2022-04-03 09:01:12",
                    "2021-12-01 13:45:32",
                    "2021-11-02 12:01:01",
                ],
                "some_other": [
                    "2022-04-01 12:00:00",
                    "2022-04-02 14:31:14",
                    "2022-04-03 09:01:12",
                    "2021-12-01 13:45:32",
                    "2021-11-02 21:01:01",
                ],
            },
            "tests": [
                {
                    "title": "basic_positive_test",
                    "exact_match_out": False,
                    "include_in_gallery": True,
                    "in": {
                        "column": "all_daytime",
                        "lat": "47.458593",
                        "lon": "19.030024",
                    },
                    "out": {
                        "success": True,
                    },
                },
                {
                    "title": "basic_negative_test",
                    "exact_match_out": False,
                    "include_in_gallery": True,
                    "in": {
                        "column": "some_other",
                        "lat": "47.458593",
                        "lon": "19.030024",
                        "mostly": 0.9,
                    },
                    "out": {
                        "success": False,
                    },
                },
            ],
        }
    ]

    # This is the id string of the Metric used by this Expectation.
    # For most Expectations, it will be the same as the `condition_metric_name` defined in your Metric class above.
    map_metric = "column_values.daytime"

    # This is a list of parameter names that can affect whether the Expectation evaluates to True or False
    success_keys = (
        "mostly",
        "lat",
        "lon",
    )

    # This dictionary contains default values for any parameters that should have default values
    default_kwarg_values = {}

    def validate_configuration(
        self, configuration: Optional[ExpectationConfiguration]
    ) -> None:
        """
        Validates that a configuration has been set, and sets a configuration if it has yet to be set. Ensures that
        necessary configuration arguments have been provided for the validation of the expectation.

        Args:
            configuration (OPTIONAL[ExpectationConfiguration]): \
                An optional Expectation Configuration entry that will be used to configure the expectation
        Returns:
            None. Raises InvalidExpectationConfigurationError if the config is not validated successfully
        """

        super().validate_configuration(configuration)
        configuration = configuration or self.configuration

        # # Check other things in configuration.kwargs and raise Exceptions if needed
        # try:
        #     assert (
        #         ...
        #     ), "message"
        #     assert (
        #         ...
        #     ), "message"
        # except AssertionError as e:
        #     raise InvalidExpectationConfigurationError(str(e))

        return True

    # This object contains metadata for display in the public Gallery
    library_metadata = {
        "maturity": "experimental",
        "tags": [
            "hackathon-22",
            "experimental",
            "typed-entities",
        ],  # Tags for this Expectation in the Gallery
        "contributors": [  # Github handles for all contributors to this Expectation.
            "@szecsip",  # Don't forget to add your github handle here!
        ],
        "requirements": ["ephem"],
    }

    success_keys = (
        "lat",
        "lon",
        "mostly",
    )


if __name__ == "__main__":
    ExpectColumnValuesToBeDaytime().print_diagnostic_checklist()
