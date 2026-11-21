"""Shared financial checks for the small fixture family."""


def validate_invoice_total(invoice):
    """Require strictly positive integer line items summing to invoice total."""
    try:
        total = invoice['total_minor']
        lines = invoice['line_items']
        if type(total) is not int or total <= 0 or not isinstance(lines, list) or not lines:
            raise ValueError('invalid invoice total')
        amounts = [line['amount_minor'] for line in lines]
        if any(type(amount) is not int or amount <= 0 for amount in amounts) or sum(amounts) != total:
            raise ValueError('invoice line items differ from total')
    except (KeyError, TypeError) as exc:
        raise ValueError('malformed invoice') from exc
