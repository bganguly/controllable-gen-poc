# TODO: implement — see PLAN.md
#
# Step 1: structured extraction (JSON mode) → Python gate (null state/price → 400)
# Step 2: TaxJar GET /v2/rates/{zip}?city=&state= → combined_rate → tax_amount
# Step 3: response generation (structured fields only, raw email NOT forwarded)
#
# Provider dispatch via X-Provider header: claude | openai | gemini
