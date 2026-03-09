"""
Quick test script to verify IBKR connection.
Run: python test_ibkr.py
"""
from ib_insync import IB, Forex, util


def test_connection():
    ib = IB()

    print("Connecting to IB Gateway...")
    try:
        ib.connect('127.0.0.1', 4002, clientId=1)
        print("[OK] Connected!")
    except Exception as e:
        print(f"[FAIL] Connection failed: {e}")
        return

    # Test account info
    print("\n--- Account Info ---")
    account_values = ib.accountSummary()
    for av in account_values:
        if av.tag in ["NetLiquidation", "TotalCashValue", "BuyingPower", "AvailableFunds"]:
            print(f"  {av.tag}: {av.value} {av.currency}")

    # Test forex contract
    print("\n--- EUR/USD Contract ---")
    contract = Forex("EURUSD")
    ib.qualifyContracts(contract)
    print(f"  Contract: {contract}")

    # Test market data
    print("\n--- Market Data ---")
    ticker = ib.reqMktData(contract, "", False, False)
    ib.sleep(2)  # Wait for data using ib_insync's sleep

    print(f"  Bid: {ticker.bid}")
    print(f"  Ask: {ticker.ask}")
    print(f"  Last: {ticker.last}")
    print(f"  Close: {ticker.close}")

    ib.cancelMktData(contract)

    # Test historical bars
    print("\n--- Historical Bars (last 5 minutes) ---")
    bars = ib.reqHistoricalData(
        contract,
        endDateTime="",
        durationStr="1 D",
        barSizeSetting="1 min",
        whatToShow="MIDPOINT",
        useRTH=False,
        formatDate=1,
    )

    if bars:
        print(f"  Got {len(bars)} bars")
        for bar in bars[-5:]:
            print(f"  {bar.date}: O={bar.open:.5f} H={bar.high:.5f} L={bar.low:.5f} C={bar.close:.5f}")
    else:
        print("  No bars received (market may be closed or no data subscription)")

    print("\n--- Disconnecting ---")
    ib.disconnect()
    print("[OK] Done!")


if __name__ == "__main__":
    util.startLoop()  # Needed for Jupyter/interactive, harmless otherwise
    test_connection()
