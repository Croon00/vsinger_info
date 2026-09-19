"""Export the accepted import contract from the administrator's Pydantic models."""

from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.admin.schemas.contracts import ImportEnvelope
from app.admin.schemas.catalog import RESOURCES, MODELS


def export():
    schema = ImportEnvelope.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    entity = schema["$defs"]["EntityInput"]
    entity["properties"]["entity_type"]["enum"] = list(RESOURCES)
    branches = []
    for name, resource in RESOURCES.items():
        for partial in (False, True):
            model = MODELS[name, partial].model_json_schema()
            schema["$defs"].update(model.pop("$defs", {}))
            for f in resource["fields"]:
                if f.get("options"):
                    model["properties"][f["name"]]["enum"] = f["options"] + (
                        [None] if f["nullable"] else []
                    )
            key = name + ("Patch" if partial else "Create")
            schema["$defs"][key] = model
        branches.append(
            {
                "if": {"properties": {"entity_type": {"const": name}}},
                "then": {
                    "if": {
                        "properties": {"operation": {"const": "update"}},
                        "required": ["operation"],
                    },
                    "then": {
                        "properties": {"data": {"$ref": "#/$defs/" + name + "Patch"}}
                    },
                    "else": {
                        "properties": {"data": {"$ref": "#/$defs/" + name + "Create"}}
                    },
                },
            }
        )
    entity["allOf"] = branches
    folder = ROOT / "schemas/import/v1"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "envelope.schema.json").write_text(
        json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (folder / "resources.json").write_text(
        json.dumps(RESOURCES, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    export()
