"""Unintegrated, read-only market-data research prototype.

This package is deliberately not wired into ASAI policy, YAML configuration,
memory, broker execution, or trading decisions.  It can only request a latest
IEX stock quote through an injected GET-only transport.
"""

from .alpaca_latest_quote import (
    ALPACA_MARKET_DATA_URL,
    IEX_FEED,
    MAX_RESPONSE_BYTES,
    AlpacaLatestIexQuoteClient,
    MarketDataConfigurationError,
    MarketDataError,
    MarketDataHttpResponse,
    MarketDataProtocolError,
    MarketDataRequestError,
    StockQuote,
)

__all__ = [
    "ALPACA_MARKET_DATA_URL",
    "IEX_FEED",
    "MAX_RESPONSE_BYTES",
    "AlpacaLatestIexQuoteClient",
    "MarketDataConfigurationError",
    "MarketDataError",
    "MarketDataHttpResponse",
    "MarketDataProtocolError",
    "MarketDataRequestError",
    "StockQuote",
]
