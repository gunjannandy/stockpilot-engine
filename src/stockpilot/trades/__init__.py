"""Trades and lots: parsers for broker documents, corporate actions, and the FIFO lot builder.
Parsers return `lots.Trade` rows; `lots.save_trades` stores them and `lots.rebuild` derives the lots."""
