import importlib.util
import json
import subprocess
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "native-game-day.py"
spec = importlib.util.spec_from_file_location("native_game_day", SCRIPT)
assert spec and spec.loader
native_game_day = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native_game_day)


class FakeRunner:
    def __init__(self, context="belacca-native"):
        self.context = context
        self.commands = []

    def __call__(self, args, **kwargs):
        self.commands.append(args)
        if args[0:3] == ["kubectl", "config", "current-context"]:
            return subprocess.CompletedProcess(args, 0, self.context + "\n", "")
        return subprocess.CompletedProcess(args, 0, "{}\n", "")


class NativeGameDaySafetyTests(unittest.TestCase):
    def test_wrong_context_fails_closed_before_any_mutation(self):
        runner = FakeRunner(context="k3d-pong")
        result = native_game_day.main(
            [
                "restart-pong-api-pod",
                "--pod",
                "pong-api-abc123",
                "--execute",
                "--ack-issue",
                "4",
                "--confirm-production",
            ],
            runner=runner,
        )
        self.assertEqual(result, 2)
        self.assertEqual(len(runner.commands), 1)
        self.assertNotIn("delete", runner.commands[0])

    def test_mutation_requires_all_explicit_gates(self):
        runner = FakeRunner()
        result = native_game_day.main(
            ["restart-pong-api-pod", "--pod", "pong-api-abc123"], runner=runner
        )
        self.assertEqual(result, 2)
        self.assertEqual(runner.commands, [])

    def test_protected_pvc_name_is_rejected_by_exact_delete_helper(self):
        for namespace, name in (
            ("pong", "pong-api-data"),
            ("untrusted-namespace", "goatcounter-data"),
            ("untrusted-namespace", "dex-data"),
            ("untrusted-namespace", "prometheus-native-data"),
        ):
            with self.subTest(namespace=namespace, name=name):
                with self.assertRaises(native_game_day.SafetyError):
                    native_game_day.delete_exact_pod(namespace, name, runner=FakeRunner())

    def test_wrong_node_is_not_accepted_as_native(self):
        with self.assertRaises(native_game_day.SafetyError):
            native_game_day.ensure_traefik_target(
                {
                    "spec": {"nodeName": "other-node"},
                    "status": {"containerStatuses": [{"ready": True}]},
                    "metadata": {"labels": {"app.kubernetes.io/name": "traefik"}},
                },
                "belacca-k3s-01",
                FakeRunner(),
            )

    def test_pong_target_requires_exact_protected_claim(self):
        pod = {
            "metadata": {
                "labels": {"app": "cloudnativepong", "component": "api"},
                "ownerReferences": [{"kind": "ReplicaSet"}],
            },
            "status": {"containerStatuses": [{"ready": True}]},
            "spec": {
                "nodeName": "belacca-k3s-01",
                "volumes": [
                    {"persistentVolumeClaim": {"claimName": "wrong-claim"}}
                ],
            },
        }
        with self.assertRaises(native_game_day.SafetyError):
            native_game_day.ensure_pong_target(pod, FakeRunner())

    def test_pong_target_rejects_multiple_ready_writers(self):
        pod = {
            "metadata": {
                "labels": {"app": "cloudnativepong", "component": "api"},
                "ownerReferences": [{"kind": "ReplicaSet"}],
            },
            "status": {"containerStatuses": [{"ready": True}]},
            "spec": {
                "nodeName": "belacca-k3s-01",
                "volumes": [{"persistentVolumeClaim": {"claimName": "pong-api-data"}}],
            },
        }

        class MultipleWriters(FakeRunner):
            def __call__(self, args, **kwargs):
                self.commands.append(args)
                if args[0:3] == ["kubectl", "config", "current-context"]:
                    return subprocess.CompletedProcess(args, 0, "belacca-native\n", "")
                if "-l" in args:
                    return subprocess.CompletedProcess(
                        args,
                        0,
                        json.dumps({
                            "items": [
                                {"status": {"containerStatuses": [{"ready": True}]}},
                                {"status": {"containerStatuses": [{"ready": True}]}},
                            ]
                        }),
                        "",
                    )
                return subprocess.CompletedProcess(args, 0, "{}\n", "")

        with self.assertRaises(native_game_day.SafetyError):
            native_game_day.ensure_pong_target(pod, MultipleWriters())


if __name__ == "__main__":
    unittest.main()
