'use strict';
(() => {
  // Prices are fixture cents; all account arithmetic remains exact integers.
  const BID = 19000, ASK = 19002, MAX_FILLS = 1000;
  const $ = id => document.getElementById(id);
  let cash = 1000000, shares = 0, count = 0;
  const money = cents => '$' + (cents / 100).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
  const clearFieldErrors = () => {
    for (const id of ['side', 'quantity', 'limit']) {
      $(id).removeAttribute('aria-invalid');
      $(id + '-error').textContent = '';
    }
  };
  const status = (text, error = false, field = null) => {
    if (field) {
      $(field).setAttribute('aria-invalid', 'true');
      $(field + '-error').textContent = text;
    }
    $('message').textContent = text;
    $('message').classList.toggle('error', error);
    // The ticket can be taller than a mobile viewport, especially with the keyboard open.
    $('message').scrollIntoView({block: 'nearest', inline: 'nearest'});
  };
  const clearFeedback = () => {
    clearFieldErrors();
    $('message').textContent = '';
    $('message').classList.remove('error');
  };
  for (const id of ['side', 'quantity', 'limit']) {
    $(id).addEventListener('input', clearFeedback);
    $(id).addEventListener('change', clearFeedback);
  }
  const parseLimit = text => {
    if (text.length > 16 || !/^(?:0|[1-9]\d{0,6})(?:\.\d{1,8})?$/.test(text)) return null;
    const [whole, fraction = ''] = text.split('.');
    const units = BigInt(whole) * 100000000n + BigInt(fraction.padEnd(8, '0'));
    return units > 0n && units <= 100000000000000n ? units : null;
  };
  const appendFill = (side, quantity, limit, fill) => {
    const row = document.createElement('tr');
    for (const value of [String(count), side, String(quantity), '$' + limit, money(fill)]) {
      const cell = document.createElement('td');
      cell.textContent = value;
      row.appendChild(cell);
    }
    $('order-rows').prepend(row);
    $('orders').hidden = false;
    $('empty').hidden = true;
    $('order-count').textContent = count + (count === 1 ? ' FILL' : ' FILLS');
  };
  $('order-form').addEventListener('submit', event => {
    event.preventDefault();
    clearFieldErrors();
    const side = $('side').value, qtyText = $('quantity').value, limitText = $('limit').value;
    if (side !== 'BUY' && side !== 'SELL') return status('Choose a valid side.', true, 'side');
    if (qtyText.length > 7 || !/^[1-9]\d{0,6}$/.test(qtyText) || Number(qtyText) > 1000000) return status('Enter a whole-share quantity from 1 to 1,000,000.', true, 'quantity');
    const quantity = Number(qtyText), limit = parseLimit(limitText);
    if (limit === null) return status('Enter a limit greater than $0 and up to $1,000,000, with at most 8 decimal places.', true, 'limit');
    if (count >= MAX_FILLS) return status('The 1,000-fill page limit is reached. Refresh to reset.', true);
    const fill = side === 'BUY' ? ASK : BID;
    const priceUnits = BigInt(fill) * 1000000n;
    if ((side === 'BUY' && limit < priceUnits) || (side === 'SELL' && limit > priceUnits)) return status('Limit is not marketable against the fixture quote. Order rejected, not queued.', true, 'limit');
    if (side === 'BUY' && quantity * fill > cash) return status('Not enough simulated cash for this order.', true, 'quantity');
    if (side === 'SELL' && quantity > shares) return status('Not enough simulated AAPL shares. Short selling is not supported.', true, 'quantity');
    if (side === 'BUY') { cash -= quantity * fill; shares += quantity; }
    else { cash += quantity * fill; shares -= quantity; }
    count++;
    $('cash').textContent = money(cash);
    $('ticket-cash').textContent = money(cash);
    $('shares').textContent = shares.toLocaleString('en-US');
    $('total').textContent = money(cash + shares * BID);
    appendFill(side, quantity, limitText, fill);
    status('Simulated ' + side.toLowerCase() + ' filled at ' + money(fill) + ' per share.');
  });
})();
