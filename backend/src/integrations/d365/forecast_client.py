import os
import requests

from .auth import get_d365_token


def get_demand_forecast(
    sku_id_range="BAK*,MEA*",
    forecast_7d_range="1..2",
    signal_range="REORDER,viral",
    max_records=100,
):
    """
    Panggil D365 getDemandForecast. Return list of dict.

    Tiap item punya field:
      SKUID, Item, Category, ADSDay, Forecast7d,
      Seasonality, Position, ROP, DaysCover, Signal
    """
    resource = os.environ["D365_RESOURCE"]
    url = f"{resource}/api/services/eyds/Forecast/getDemandForecast"

    resp = requests.post(
        url,
        json={
            "_filter": {
                "SKUIDRange": sku_id_range,
                "Forecast7dRange": forecast_7d_range,
                "SignalRange": signal_range,
                "MaxRecords": max_records,
            }
        },
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {get_d365_token()}",
        },
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()


    if isinstance(data, dict) and "value" in data:
        return data["value"]
    return data


def summarize_forecast(rows, max_records=100):
    """
    Summarize forecast results into compact numbers for the agent.
    Reorder = Position below ROP.

    possibly_truncated is True when the number of returned rows is >=
    max_records, which means more SKUs may have been cut off by the limit.
    """
    reorder = [r for r in rows if r.get("Position", 0) < r.get("ROP", 0)]
    viral = [r for r in rows if str(r.get("Signal", "")).lower() == "viral"]

    return {
        "total_sku": len(rows),
        "possibly_truncated": len(rows) >= max_records,
        "reorder_count": len(reorder),
        "viral_count": len(viral),
        "reorder_skus": [
            {
                "sku": r.get("SKUID"),
                "item": r.get("Item"),
                "category": r.get("Category"),
                "position": r.get("Position"),
                "rop": r.get("ROP"),
                "days_cover": r.get("DaysCover"),
                "signal": r.get("Signal"),
            }
            for r in reorder
        ],
    }