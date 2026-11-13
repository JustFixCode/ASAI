"""Compare browser order results with the Python simulator."""
from datetime import datetime, timezone
from decimal import Decimal
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from demo.simulator import DemoError, DemoQuote, DemoSimulator

async def differential(c):
    # Compare a deterministic adversarial sequence against the actual Python simulator.
    sim = DemoSimulator()
    now = datetime.now(timezone.utc)
    quote = DemoQuote('AAPL', Decimal('190.00'), Decimal('190.02'), now, now, 'fixture')
    rng = random.Random(20261113)
    prices = ['0.00000001', '189.99999999', '190', '190.00000001',
              '190.01999999', '190.02', '190.02000001', '1000000']
    cases = [('BUY', 52, '190.02'), ('BUY', 1, '190.02'),
             ('SELL', 53, '190'), ('SELL', 52, '190')]
    cases += [(rng.choice(['BUY', 'SELL']), rng.choice([1, 2, 10, 52, 53, 1000000]), rng.choice(prices)) for _ in range(160)]
    errors = {'LIMIT_NOT_MARKETABLE': 'not marketable',
              'INSUFFICIENT_CASH': 'not enough simulated cash',
              'INSUFFICIENT_POSITION': 'not enough simulated aapl shares'}
    for i, (side, quantity, price) in enumerate(cases):
        try:
            sim.place_order({'symbol': 'AAPL', 'side': side, 'quantity': quantity, 'limit_price': price}, str(i), quote, now)
            expected = 'filled at'
        except DemoError as exc:
            expected = errors[exc.code]
        result = await c.js("""(() => {document.querySelector('#side').value=%s; document.querySelector('#quantity').value=%s; document.querySelector('#limit').value=%s; document.querySelector('#order-form').requestSubmit(); return {message: document.querySelector('#message').textContent.toLowerCase(), cash: document.querySelector('#cash').textContent, shares: document.querySelector('#shares').textContent, total: document.querySelector('#total').textContent, rows: document.querySelectorAll('#order-rows tr').length}})()""" % tuple(json.dumps(v) for v in (side, str(quantity), price)))
        state = sim.snapshot()
        cash = Decimal(state['cash'])
        shares = state['positions']['AAPL']
        assert expected in result['message'], (i, side, quantity, price, expected, result)
        assert result['cash'] == f'${cash:,.2f}' and result['shares'] == f'{shares:,}'
        assert result['total'] == f'${cash + shares * Decimal("190.00"):,.2f}'
        assert result['rows'] == len(state['orders'])
    print(f'PASS: {len(cases)} orders compared with the Python simulator')
