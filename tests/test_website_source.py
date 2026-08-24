from __future__ import annotations

import unittest
from datetime import UTC, datetime

from coned_scraper.models import ReadingQuality, SourceName
from coned_scraper.sources.website import (
    GraphQLSelection,
    _daily_window,
    _graphql_headers,
    parse_daily_usage,
    parse_daily_weather,
    parse_graphql_readings,
    parse_metadata,
    parse_register_id,
)


class WebsiteGraphQLParsingTests(unittest.TestCase):
    def test_graphql_headers_select_authenticated_customer_entity(self) -> None:
        headers = _graphql_headers("token", "customer-uuid")

        self.assertEqual(
            '["urn:opower:customer:uuid:customer-uuid"]',
            headers["Opower-Selected-Entities"],
        )

    def test_metadata_selects_first_electric_service_point(self) -> None:
        payload = {
            "data": {
                "billingAccountByAuthContext": {
                    "premisesConnection": {"edges": [{"node": {"uuid": "premise-1"}}]},
                    "serviceAgreementsConnection": {
                        "edges": [
                            {
                                "node": {
                                    "uuid": "gas-sa",
                                    "serviceType": "GAS",
                                    "servicePointsConnection": {
                                        "edges": [{"node": {"uuid": "gas-sp"}}]
                                    },
                                }
                            },
                            {
                                "node": {
                                    "uuid": "electric-sa",
                                    "serviceType": "ELECTRIC",
                                    "servicePointsConnection": {
                                        "edges": [{"node": {"uuid": "electric-sp"}}]
                                    },
                                }
                            },
                        ]
                    },
                }
            }
        }

        self.assertEqual(
            GraphQLSelection("electric-sa", "electric-sp", "premise-1"),
            parse_metadata(payload),
        )

    def test_daily_window_uses_new_york_calendar_days(self) -> None:
        now = datetime(2026, 8, 23, 14, tzinfo=UTC)
        self.assertEqual(
            "2026-08-21T00:00:00-04:00/2026-08-24T00:00:00-04:00",
            _daily_window(3, now),
        )

    def test_daily_usage_and_weather_parsers(self) -> None:
        usage = {
            "data": {
                "billingAccountByAuthContext": {
                    "serviceAgreementsConnection": {
                        "edges": [
                            {
                                "node": {
                                    "servicePointsConnection": {
                                        "edges": [
                                            {
                                                "node": {
                                                    "readStreams": [
                                                        {
                                                            "netUsage": {
                                                                "unit": "KWH",
                                                                "reads": [
                                                                    {
                                                                        "timeInterval": "2026-08-22T00:00:00-04:00/2026-08-23T00:00:00-04:00",
                                                                        "measuredAmount": {
                                                                            "value": 12.5,
                                                                            "unit": "KWH",
                                                                        },
                                                                    }
                                                                ],
                                                            }
                                                        }
                                                    ]
                                                }
                                            }
                                        ]
                                    }
                                }
                            }
                        ]
                    }
                }
            }
        }
        weather = {
            "data": {
                "billingAccountByAuthContext": {
                    "premisesConnection": {
                        "edges": [
                            {
                                "node": {
                                    "weather": [
                                        {
                                            "timeInterval": "2026-08-22T00:00:00-04:00/2026-08-23T00:00:00-04:00",
                                            "minTemperature": {"value": 68},
                                            "meanTemperature": {"value": 75},
                                            "maxTemperature": {"value": 82},
                                        }
                                    ]
                                }
                            }
                        ]
                    }
                }
            }
        }

        usage_result = parse_daily_usage(usage, account_id="account-1")
        weather_result = parse_daily_weather(
            weather, account_id="account-1", premise_uuid="premise-1"
        )

        self.assertEqual(12.5, usage_result[0].energy_kwh)
        self.assertEqual(68.0, weather_result[0].minimum_temperature_f)
        self.assertEqual(75.0, weather_result[0].mean_temperature_f)
        self.assertEqual(82.0, weather_result[0].maximum_temperature_f)

    def test_register_parser_uses_first_nonempty_register(self) -> None:
        payload = {
            "data": {
                "billingAccountByAuthContext": {
                    "serviceAgreementsConnection": {
                        "edges": [
                            {
                                "node": {
                                    "servicePointsConnection": {
                                        "edges": [
                                            {
                                                "node": {
                                                    "intervalReads": [
                                                        {"registerId": None},
                                                        {"registerId": "register-1"},
                                                    ]
                                                }
                                            }
                                        ]
                                    }
                                }
                            }
                        ]
                    }
                }
            }
        }

        self.assertEqual("register-1", parse_register_id(payload))

    def test_read_parser_filters_null_values_and_derives_power(self) -> None:
        payload = {
            "data": {
                "billingAccountByAuthContext": {
                    "serviceAgreementsConnection": {
                        "edges": [
                            {
                                "node": {
                                    "servicePointsConnection": {
                                        "edges": [
                                            {
                                                "node": {
                                                    "intervalReads": [
                                                        {
                                                            "unit": "KWH",
                                                            "registerId": "register-1",
                                                            "reads": [
                                                                {
                                                                    "timeInterval": "2026-08-23T11:45:00Z/2026-08-23T12:00:00Z",
                                                                    "measuredAmount": {
                                                                        "value": 0.072
                                                                    },
                                                                },
                                                                {
                                                                    "timeInterval": "2026-08-23T12:00:00Z/2026-08-23T12:15:00Z",
                                                                    "measuredAmount": None,
                                                                },
                                                            ],
                                                        }
                                                    ]
                                                }
                                            }
                                        ]
                                    }
                                }
                            }
                        ]
                    }
                }
            }
        }

        result = parse_graphql_readings(
            payload,
            account_id="account-1",
            fetched_at=datetime(2026, 8, 24, 2, 0, tzinfo=UTC),
        )

        self.assertEqual(1, len(result))
        self.assertEqual(0.072, result[0].energy_kwh)
        self.assertEqual(288.0, result[0].average_power_w)
        self.assertEqual(SourceName.WEBSITE_API, result[0].source)
        self.assertEqual(ReadingQuality.MEASURED, result[0].quality)
        self.assertEqual(15, result[0].source_resolution_minutes)


if __name__ == "__main__":
    unittest.main()
