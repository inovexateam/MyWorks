# parse_copilot_tokens.py
import json, sys

with open(sys.argv[1]) as f:
    data = json.load(f)

for span in data.get("resourceSpans", []):
    for scope in span.get("scopeSpans", []):
        for s in scope.get("spans", []):
            attrs = {a["key"]: list(a["value"].values())[0]
                     for a in s.get("attributes", [])}
            tokens_in  = attrs.get("gen_ai.usage.input_tokens")
            tokens_out = attrs.get("gen_ai.usage.output_tokens")
            model      = attrs.get("gen_ai.request.model", "")
            name       = s.get("name", "")
            if tokens_in or tokens_out:
                print(f"{name} | model={model} | in={tokens_in} out={tokens_out}")