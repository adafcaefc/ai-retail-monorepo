from dotenv import load_dotenv
load_dotenv()

import json
from src.llm.agents.retail.retail.tools.demand_forecast import query_demand_forecast

result = query_demand_forecast(limit=15)
print(json.dumps(result["summary"], indent=2))