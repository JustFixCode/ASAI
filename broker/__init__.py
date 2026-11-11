"""Fail-closed Alpaca paper-stock adapter foundation.

This package supports only Alpaca's paper-trading REST hostname and US stock order
payloads.  It is deliberately low-level; it provides no autonomous risk gate,
portfolio policy, reconciliation, or regulatory/deployment controls.
"""

from .alpaca_paper import (
    ALPACA_PAPER_HOST,
    ALPACA_PAPER_URL,
    AlpacaPaperStocksClient,
    BrokerConfigurationError,
    BrokerError,
    BrokerProtocolError,
    BrokerRequestError,
    BrokerTimeoutUnknownStatus,
    HttpResponse,
    OrderRequest,
    PAPER_STOCKS_ONLY_NOTICE,
)

__all__ = [
    "ALPACA_PAPER_HOST",
    "ALPACA_PAPER_URL",
    "AlpacaPaperStocksClient",
    "BrokerConfigurationError",
    "BrokerError",
    "BrokerProtocolError",
    "BrokerRequestError",
    "BrokerTimeoutUnknownStatus",
    "HttpResponse",
    "OrderRequest",
    "PAPER_STOCKS_ONLY_NOTICE",
]
