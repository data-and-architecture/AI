from agent.metadata_loader import MetadataLoader

m = MetadataLoader("metadata").load()

print("search_dimensions('team'):", [d["id"] for d in m.search_dimensions("team")])
print("search_metrics('pay'):", [d["id"] for d in m.search_metrics("pay")])
print("search_dimensions('organizational unit'):", [d["id"] for d in m.search_dimensions("organizational unit")])
print("search_terms('staff'):", [t["id"] for t in m.search_terms("staff")])