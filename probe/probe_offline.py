"""Offline introspection probe: answers what can be answered without a billed call."""
import inspect

import google.antigravity as agy
from google.antigravity import types
from google.antigravity.hooks import policy


def dump_model(name, cls):
    print(f"\n{'='*70}\n{name}  ({cls.__module__}.{cls.__qualname__})\n{'='*70}")
    fields = getattr(cls, "model_fields", None)
    if fields is None:
        print("  not a pydantic model; signature:", inspect.signature(cls))
        return
    for fname, f in fields.items():
        ann = getattr(f, "annotation", "?")
        default = getattr(f, "default", None)
        desc = (getattr(f, "description", None) or "").strip()
        print(f"  {fname}: {ann}")
        print(f"      default={default!r}")
        if desc:
            print(f"      doc: {desc}")


def dump_enum(name, e):
    print(f"\n{'='*70}\n{name}\n{'='*70}")
    for m in e:
        print(f"  {m.name} = {m.value!r}")


print("SDK module file:", agy.__file__)
print("types exports containing 'Label':",
      [n for n in dir(types) if "abel" in n])
print("top-level exports:", [n for n in dir(agy) if not n.startswith("_")])

for nm in ["BudgetConfig", "CapabilitiesConfig", "SubagentCapabilities",
           "RetryConfig", "ModelAPIRetryConfig", "ModelOutputRetryConfig",
           "GeminiModelOptions", "UsageMetadata"]:
    cls = getattr(types, nm, None)
    if cls is None:
        print(f"\n!! types.{nm} NOT FOUND")
    else:
        dump_model(nm, cls)

for nm in ["BuiltinTools", "StopReason", "ServiceTier", "AgentBehavior"]:
    e = getattr(types, nm, None)
    if e is None:
        print(f"\n!! types.{nm} NOT FOUND")
    else:
        dump_enum(nm, e)

print(f"\n{'='*70}\npolicy.allow signature\n{'='*70}")
print(" ", inspect.signature(policy.allow))
print("  doc:", (policy.allow.__doc__ or "").strip()[:900])

# Q11: hunt for any label surface anywhere in the config surface
print(f"\n{'='*70}\nQ11: label-ish attributes across types\n{'='*70}")
hits = []
for nm in dir(types):
    cls = getattr(types, nm, None)
    mf = getattr(cls, "model_fields", None)
    if isinstance(mf, dict):
        for f in mf:
            if "label" in f.lower() or "tag" in f.lower() or "metadata" in f.lower():
                hits.append(f"types.{nm}.{f}")
print("  " + ("\n  ".join(hits) if hits else "NONE FOUND"))

# LocalAgentConfig full field list
from google.antigravity import LocalAgentConfig

dump_model("LocalAgentConfig", LocalAgentConfig)
