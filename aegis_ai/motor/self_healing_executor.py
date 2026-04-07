import yaml
import subprocess

class SelfHealingExecutor:

    def execute(self, yaml_patch: str):
        patch = yaml.safe_load(yaml_patch)

        for action in patch["actions"]:

            if action["type"] == "rollback_migration":
                subprocess.call(["./scripts/rollback.sh", action["zone"]])

            if action["type"] == "retrain_model":
                subprocess.call(["./scripts/retrain_model.sh"])

            if action["type"] == "update_feature_store":
                subprocess.call(["./scripts/update_features.sh"] + action["features"])
