from dotenv import load_dotenv
load_dotenv()

from src.llm.agents.retail.retail.tools.demand_forecast import query_demand_forecast

result = query_demand_forecast(sku="*", limit=100)
rows = result["rows"]
summary = result["summary"]

# Header
print(f"\n{'SKUID':<10} {'Item':<24} {'Cat':<5} {'Pos':>8} {'ROP':>6} {'Cover':>6} {'Signal':<8}")
print("-" * 75)

# Sort by DaysCover (most urgent first), then by shortfall
for r in sorted(rows, key=lambda x: (x.get("DaysCover", 999), -(x.get("ROP", 0) - x.get("Position", 0)))):
    print(
        f"{r['SKUID']:<10} {r['Item'][:23]:<24} {r['Category']:<5} "
        f"{r['Position']:>8} {r['ROP']:>6} {r['DaysCover']:>6} {r['Signal']:<8}"
    )

# Summary
print("-" * 75)
print(f"\nTotal SKU        : {summary['total_sku']}")
print(f"Reorder needed   : {summary['reorder_count']}")
print(f"Viral            : {summary['viral_count']}")
print(f"Possibly cut off : {summary['possibly_truncated']}")

# Category breakdown
cats = {}
for r in rows:
    cats[r["Category"]] = cats.get(r["Category"], 0) + 1
print(f"\nCategories: " + ", ".join(f"{k}={v}" for k, v in sorted(cats.items())))