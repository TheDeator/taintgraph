# Example session (anonymised)

What a white-box session looks like once you have built the extractors + `graphquery`
from the contract. Identifiers are illustrative.

## 1. Recon + build the graph (no target build needed for the regex tier)
```
$ build-graph-cs.sh /path/to/src graph.db
nodes|3522
edges|224719
sources|1799
sinks|1604
boundaries|509
dependencies|142
```

## 2. Trace a sink back to a source
```
$ graphquery --db graph.db trace-back ExecuteSqlRaw
### SINK Billing.Api.Orders.OrderController.Submit
  REACHABLE from source [route: POST /api/orders]
     Billing.Api.Orders.OrderController.Submit
```
A "NO STATIC PATH" is NOT "safe" — it prints the stop reason (dead-end vs boundary):
```
### SINK Infra.Migrations.AddColumn.Run
  NO STATIC PATH TO A SOURCE  (NOT proof of safety — verify, see AGENT_NOTES C)
     stop: Infra.Migrations.AddColumn.Run  [boundary:reflection:Activator.CreateInstance]
```

## 3. Who calls / what calls (instead of repeated grep)
```
$ graphquery --db graph.db callers OrderService.PlaceOrder
Billing.Api.Orders.OrderController.Submit   <-call/static-exact--   Billing.App.OrderService.PlaceOrder
```

## 4. High-fidelity tier (optional): engine findings in the same store
```
$ build-semgrep.sh /path/to/src graph.db cs
semgrep findings|8
$ graphquery --db graph.db findings all
[semgrep:ERROR] cs-sqli-concat-raw  .../OrderRepo.cs:44
    node Billing.Infra.OrderRepo.RawQuery  ENGINE-FLAGGED but regex graph finds NO path
      -> likely regex-tier false-negative (L1); trust the engine (precedence §6.5)
```

## 5. Seeded exploration of the uncertainty frontier (bounded tokens)
```
$ graphquery --db graph.db explore --seed 7 --explore-budget 12
# exploration targets  seed=7  budget=12  frontier_size=531
[boundary] Gateway.Proxy.Forward   (grpc-cross-service:client-call)
[isolated-sink] Reporting.Export.Dump   (path:File.WriteAllText)  <-- also engine-flagged
```

## 6. Self-correct the graph (never edits facts)
```
$ graphquery --db graph.db annotate-add Gateway.Proxy.Forward Billing.App.OrderService.PlaceOrder \
    --reason "resolved reflection dispatch by hand" --evidence Proxy.cs:88 --mech reflection
[add] ... recorded. Fact layer untouched; re-run extractors anytime, this overlay persists.
```
