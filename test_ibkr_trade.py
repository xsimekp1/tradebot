"""
Test placing a small forex order on IBKR paper account.
"""
from ib_insync import IB, Forex, MarketOrder, util


def test_trade():
    ib = IB()

    print("Connecting to IB Gateway...")
    ib.connect('127.0.0.1', 4002, clientId=2)
    print("[OK] Connected!")

    # Create EUR/USD contract
    contract = Forex("EURUSD")
    ib.qualifyContracts(contract)
    print(f"Contract: {contract}")

    # Get current price
    ticker = ib.reqMktData(contract, "", False, False)
    ib.sleep(2)
    print(f"Current price - Bid: {ticker.bid}, Ask: {ticker.ask}")

    # Place a small BUY order (20,000 EUR - minimum for IBKR forex)
    print("\n--- Placing BUY order for 20,000 EUR ---")
    buy_order = MarketOrder("BUY", 20000)
    trade = ib.placeOrder(contract, buy_order)

    # Wait for fill
    ib.sleep(3)
    print(f"Order status: {trade.orderStatus.status}")
    print(f"Filled: {trade.orderStatus.filled}")
    print(f"Avg fill price: {trade.orderStatus.avgFillPrice}")

    # Check position
    print("\n--- Current Positions ---")
    positions = ib.positions()
    for pos in positions:
        print(f"  {pos.contract.symbol}: {pos.position} @ {pos.avgCost}")

    # Close the position - SELL the same amount
    print("\n--- Closing position (SELL 20,000 EUR) ---")
    sell_order = MarketOrder("SELL", 20000)
    trade2 = ib.placeOrder(contract, sell_order)

    ib.sleep(3)
    print(f"Order status: {trade2.orderStatus.status}")
    print(f"Filled: {trade2.orderStatus.filled}")
    print(f"Avg fill price: {trade2.orderStatus.avgFillPrice}")

    # Final positions
    print("\n--- Final Positions ---")
    positions = ib.positions()
    if positions:
        for pos in positions:
            print(f"  {pos.contract.symbol}: {pos.position} @ {pos.avgCost}")
    else:
        print("  No open positions")

    print("\n--- Disconnecting ---")
    ib.disconnect()
    print("[OK] Done!")


if __name__ == "__main__":
    util.startLoop()
    test_trade()
